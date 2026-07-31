import json
import logging
import os
import signal
import threading
import time

import redis
import requests

from .clip_extractor import ensure_bucket, make_s3_client
from .commands import WORKER_EVENTS_CHANNEL, CommandListener
from .config import WorkerConfig, load_config
from .ring_buffer import FrameRingBuffer
from .rtsp_reader import RtspReader

logger = logging.getLogger("worker")

STATUS_INTERVAL_SECONDS = 10.0


def fetch_stream_url(config: WorkerConfig) -> str:
    """Récupère l'URL RTSP déchiffrée auprès de l'API (retry tant que la caméra n'existe pas)."""
    url = f"{config.api_url}/cameras/{config.camera_id}/stream-url"
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
    listener = CommandListener(config, buffer, s3)
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
        stop.wait(STATUS_INTERVAL_SECONDS)

    logger.info("shutting down")
    reader.stop()
    listener.stop()
    reader.join(timeout=5)
    listener.join(timeout=5)


if __name__ == "__main__":
    main()
