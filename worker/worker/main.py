import json
import logging
import os
import signal
import threading
import time

import redis
import requests

from .alerts import AlertEmitter
from .clip_extractor import ensure_bucket, make_s3_client
from .commands import WORKER_EVENTS_CHANNEL, CommandListener
from .config import WorkerConfig, load_config
from .ring_buffer import FrameRingBuffer
from .rtsp_reader import RtspReader
from .rules_engine import RulesConfig, RulesEngine
from .zone_tracker import Zone, ZoneTracker

logger = logging.getLogger("worker")

STATUS_INTERVAL_SECONDS = 10.0


def fetch_stream_url(config: WorkerConfig) -> str:
    """Récupère l'URL RTSP déchiffrée auprès de l'API (retry tant que la caméra n'existe pas)."""
    url = f"{config.api_url}/internal/cameras/{config.camera_id}/stream-url"
    while True:
        try:
            response = requests.get(
                url, headers={"X-API-Key": config.api_key}, timeout=10
            )
            if response.status_code == 200:
                return response.json()["rtsp_url"]
            logger.warning(
                "camera %s not available from API (HTTP %d), retrying in 5s",
                config.camera_id,
                response.status_code,
            )
        except requests.RequestException as exc:
            logger.warning("API unreachable (%s), retrying in 5s", exc)
        time.sleep(5)


def fetch_zones(config: WorkerConfig) -> list[Zone]:
    """Zones configurées pour la caméra (les mises à jour arrivent ensuite via Redis)."""
    url = f"{config.api_url}/internal/cameras/{config.camera_id}/zones"
    try:
        response = requests.get(url, headers={"X-API-Key": config.api_key}, timeout=10)
        response.raise_for_status()
        return [Zone.from_dict(z) for z in response.json()]
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.warning("could not fetch zones (%s), starting with none", exc)
        return []


def fetch_settings(config: WorkerConfig) -> dict:
    """Seuils par caméra (SPEC §6) ; les mises à jour arrivent ensuite via Redis."""
    url = f"{config.api_url}/internal/cameras/{config.camera_id}/settings"
    try:
        response = requests.get(url, headers={"X-API-Key": config.api_key}, timeout=10)
        response.raise_for_status()
        return response.json() or {}
    except (requests.RequestException, ValueError) as exc:
        logger.warning("could not fetch settings (%s), using defaults", exc)
        return {}


def build_analysis(
    config: WorkerConfig,
    reader: RtspReader,
    zone_tracker: ZoneTracker,
    rules_engine: RulesEngine,
    alert_emitter: AlertEmitter,
):
    """Construit le pipeline d'analyse, ou None si désactivé / dépendances absentes."""
    if not config.analysis_enabled:
        logger.info("analysis disabled (ANALYSIS_ENABLED=false)")
        return None
    try:
        from .analysis import AnalysisPipeline
        from .detection import ObjectDetector, PersonDetector

        detector = PersonDetector(config.yolo_model)
        object_detector = (
            ObjectDetector(config.object_model, confidence=config.object_confidence)
            if config.objects_enabled
            else None
        )
    except Exception:
        logger.exception("failed to initialize detection, analysis disabled")
        return None
    return AnalysisPipeline(
        config,
        reader,
        detector,
        zone_tracker,
        rules_engine,
        object_detector=object_detector,
        alert_sink=alert_emitter.emit,
    )


def upload_snapshot(config: WorkerConfig, buffer: FrameRingBuffer, s3) -> None:
    """Publie la dernière frame en `{camera_id}/snapshot.jpg` (éditeur de zones)."""
    newest_ts = buffer.newest_ts
    if newest_ts is None:
        return
    frames = buffer.snapshot(newest_ts, newest_ts)
    if not frames:
        return
    try:
        s3.put_object(
            Bucket=config.s3_bucket,
            Key=f"{config.camera_id}/snapshot.jpg",
            Body=frames[-1][1],
            ContentType="image/jpeg",
        )
    except Exception as exc:
        logger.warning("failed to upload snapshot: %s", exc)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    while not os.environ.get("CAMERA_ID"):
        logger.warning(
            "CAMERA_ID is not set — register a camera via the API, put its id in "
            "WORKER_CAMERA_ID (.env) and restart. Sleeping 30s."
        )
        time.sleep(30)

    config = load_config()
    rtsp_url = fetch_stream_url(config)

    buffer = FrameRingBuffer(config.buffer_seconds, config.target_fps)
    s3 = make_s3_client(
        config.s3_endpoint_url, config.s3_access_key, config.s3_secret_key
    )
    ensure_bucket(s3, config.s3_bucket)

    reader = RtspReader(rtsp_url, buffer, config.target_fps, config.jpeg_quality)
    reader.start()

    camera_settings = fetch_settings(config)
    zone_tracker = ZoneTracker(
        zones=fetch_zones(config),
        dwell_seconds=camera_settings.get("dwell_seconds", config.dwell_seconds),
        track_ttl=config.track_ttl_seconds,
    )
    rules_engine = RulesEngine(RulesConfig.from_dict(camera_settings))
    alert_emitter = AlertEmitter(config, buffer, s3)

    analysis = build_analysis(config, reader, zone_tracker, rules_engine, alert_emitter)
    if analysis is not None:
        analysis.start()

    def apply_settings(settings: dict) -> None:
        rules_engine.update_config(RulesConfig.from_dict(settings))
        if "dwell_seconds" in settings:
            zone_tracker.set_dwell_seconds(float(settings["dwell_seconds"]))

    listener = CommandListener(
        config,
        buffer,
        s3,
        on_update_zones=lambda zones: zone_tracker.update_zones(
            [Zone.from_dict(z) for z in zones]
        ),
        on_update_settings=apply_settings,
    )
    listener.start()

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    status_client = redis.Redis.from_url(config.redis_url)
    while not stop.is_set():
        status = "online" if reader.connected else "offline"
        try:
            status_client.publish(
                WORKER_EVENTS_CHANNEL,
                json.dumps(
                    {
                        "type": "camera_status",
                        "camera_id": config.camera_id,
                        "status": status,
                        "buffered_frames": len(buffer),
                    }
                ),
            )
        except redis.RedisError as exc:
            logger.warning("failed to publish status: %s", exc)
        upload_snapshot(config, buffer, s3)
        stop.wait(STATUS_INTERVAL_SECONDS)

    logger.info("shutting down")
    reader.stop()
    listener.stop()
    if analysis is not None:
        analysis.stop()
        analysis.join(timeout=5)
    reader.join(timeout=5)
    listener.join(timeout=5)


if __name__ == "__main__":
    main()
