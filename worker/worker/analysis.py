"""Thread d'analyse : YOLO + ByteTrack sur la dernière frame, événements de zones."""

import json
import logging
import threading
import time

import redis

from .config import WorkerConfig
from .zone_tracker import ZoneTracker

logger = logging.getLogger(__name__)

ANALYSIS_EVENTS_CHANNEL = "analysis_events"


class AnalysisPipeline(threading.Thread):
    """Consomme la dernière frame du lecteur RTSP au rythme `analysis_fps`,
    exécute détection + tracking, alimente le ZoneTracker et publie les
    événements de zones sur Redis (canal `analysis_events`).

    Les positions ne sont jamais persistées : elles vivent le temps d'une frame.
    """

    def __init__(
        self,
        config: WorkerConfig,
        reader,
        detector,
        zone_tracker: ZoneTracker,
    ):
        super().__init__(daemon=True, name="analysis")
        self._config = config
        self._reader = reader
        self._detector = detector
        self._zone_tracker = zone_tracker
        self._redis = redis.Redis.from_url(config.redis_url)
        self._interval = 1.0 / config.analysis_fps
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        logger.info("analysis pipeline started (%.1f fps max)", 1.0 / self._interval)
        last_ts = 0.0
        while not self._stop.is_set():
            started = time.time()
            latest = self._reader.latest_frame()
            if latest is None or latest[0] == last_ts:
                self._stop.wait(0.05)
                continue
            ts, frame = latest
            last_ts = ts

            try:
                detections = self._detector.track(frame)
                events = self._zone_tracker.process(ts, detections)
            except Exception:
                logger.exception("analysis failed on frame %.3f", ts)
                self._stop.wait(1.0)
                continue

            for event in events:
                event["camera_id"] = self._config.camera_id
                logger.info(
                    "%s track=%s zone=%s (%s)%s",
                    event["type"],
                    event["track_id"],
                    event["zone_name"],
                    event["zone_type"],
                    f" duration={event['duration_seconds']}s"
                    if event.get("duration_seconds") is not None
                    else "",
                )
                try:
                    self._redis.publish(ANALYSIS_EVENTS_CHANNEL, json.dumps(event))
                except redis.RedisError as exc:
                    logger.warning("failed to publish analysis event: %s", exc)

            elapsed = time.time() - started
            if elapsed < self._interval:
                self._stop.wait(self._interval - elapsed)
