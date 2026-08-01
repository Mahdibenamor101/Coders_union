"""Thread d'analyse : perception (YOLO pose + objets), zones, moteur de règles."""

import json
import logging
import threading
import time

import redis

from .config import WorkerConfig
from .perception import GestureMonitor, MovementTracker, ObjectAssociationTracker
from .rules_engine import RulesEngine
from .zone_tracker import ZoneTracker

logger = logging.getLogger(__name__)

ANALYSIS_EVENTS_CHANNEL = "analysis_events"


class AnalysisPipeline(threading.Thread):
    """Consomme la dernière frame du lecteur RTSP au rythme `analysis_fps` et
    enchaîne : détection de personnes (pose) → événements de zones + perception
    (objets saisis/dissimulés, gestes) → moteur de règles → alertes.

    Les positions et keypoints ne sont jamais persistés : ils vivent le temps
    d'une frame (ou d'une fenêtre glissante en mémoire pour le mouvement).
    """

    def __init__(
        self,
        config: WorkerConfig,
        reader,
        detector,
        zone_tracker: ZoneTracker,
        rules_engine: RulesEngine,
        object_detector=None,
        alert_sink=None,
    ):
        super().__init__(daemon=True, name="analysis")
        self._config = config
        self._reader = reader
        self._detector = detector
        self._object_detector = object_detector
        self._zone_tracker = zone_tracker
        self._rules_engine = rules_engine
        self._alert_sink = alert_sink
        self._association = ObjectAssociationTracker()
        self._gestures = GestureMonitor()
        self._movement = MovementTracker()
        self._redis = redis.Redis.from_url(config.redis_url)
        self._interval = 1.0 / config.analysis_fps
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        logger.info("analysis pipeline started (%.1f fps max)", 1.0 / self._interval)
        last_ts = 0.0
        frame_index = 0
        while not self._stop.is_set():
            started = time.time()
            latest = self._reader.latest_frame()
            if latest is None or latest[0] == last_ts:
                self._stop.wait(0.05)
                continue
            ts, frame = latest
            last_ts = ts
            frame_index += 1

            try:
                events = self._analyze(ts, frame, frame_index)
            except Exception:
                logger.exception("analysis failed on frame %.3f", ts)
                self._stop.wait(1.0)
                continue

            for event in events:
                self._publish(event)
                for decision in self._rules_engine.process(event):
                    logger.warning(
                        "alert decision rule=%s score=%.1f track=%s",
                        decision.rule,
                        decision.score,
                        decision.track_id,
                    )
                    if self._alert_sink is not None:
                        self._alert_sink(decision)

            elapsed = time.time() - started
            if elapsed < self._interval:
                self._stop.wait(self._interval - elapsed)

    def _analyze(self, ts: float, frame, frame_index: int) -> list[dict]:
        persons = self._detector.track(frame)

        for person in persons:
            self._movement.add(ts, person.track_id, *person.foot)

        zone_events = self._zone_tracker.process(
            ts, [(p.track_id, p.foot[0], p.foot[1]) for p in persons]
        )
        for event in zone_events:
            if event["type"] == "person_dwell":
                event["movement_radius"] = self._movement.radius(event["track_id"])

        perception_events: list[dict] = []
        if (
            self._object_detector is not None
            and frame_index % self._config.object_every_n == 0
        ):
            objects = self._object_detector.detect(frame)
            perception_events.extend(self._association.update(ts, persons, objects))

        for person in persons:
            gesture = self._gestures.update(ts, person.track_id, person.head_dir)
            if gesture is not None:
                perception_events.append(gesture)

        return zone_events + perception_events

    def _publish(self, event: dict) -> None:
        event["camera_id"] = self._config.camera_id
        logger.info(
            "%s track=%s%s",
            event["type"],
            event.get("track_id"),
            f" zone={event['zone_name']} ({event['zone_type']})"
            if "zone_name" in event
            else f" object={event['object_class']}"
            if "object_class" in event
            else "",
        )
        try:
            self._redis.publish(ANALYSIS_EVENTS_CHANNEL, json.dumps(event))
        except redis.RedisError as exc:
            logger.warning("failed to publish analysis event: %s", exc)
