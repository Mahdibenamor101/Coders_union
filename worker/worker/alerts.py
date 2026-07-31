"""Émission d'alertes : clip + thumbnail depuis le buffer, upload, publication."""

import json
import logging
import os
import tempfile
import threading
import time
import uuid

import redis

from .clip_extractor import build_clip, upload_clip
from .commands import WORKER_EVENTS_CHANNEL
from .config import WorkerConfig
from .ring_buffer import FrameRingBuffer
from .rules_engine import AlertDecision

logger = logging.getLogger(__name__)


class AlertEmitter:
    """Matérialise une décision du moteur de règles : attend la fin de la fenêtre
    « après », découpe le clip et la thumbnail depuis le buffer circulaire,
    uploade sur S3/MinIO, puis publie `behavior_alert` sur `worker_events`.

    Une alerte sans frames disponibles est publiée quand même (sans clip) :
    la revue humaine doit voir que quelque chose a été signalé.
    """

    def __init__(self, config: WorkerConfig, buffer: FrameRingBuffer, s3):
        self._config = config
        self._buffer = buffer
        self._s3 = s3
        self._redis = redis.Redis.from_url(config.redis_url)

    def emit(self, decision: AlertDecision) -> None:
        threading.Thread(
            target=self._process, args=(decision,), daemon=True, name="alert-emitter"
        ).start()

    def _process(self, decision: AlertDecision) -> None:
        alert_id = str(uuid.uuid4())
        pre = self._config.alert_clip_pre_seconds
        post = self._config.alert_clip_post_seconds

        remaining = decision.ts + post - time.time()
        if remaining > 0:
            time.sleep(remaining)

        clip_key = thumbnail_key = None
        frame_count = 0
        try:
            frames = self._buffer.snapshot(decision.ts - pre, decision.ts + post)
            frame_count = len(frames)
            if frames:
                clip_key, thumbnail_key = self._build_media(alert_id, decision, frames)
        except Exception:
            logger.exception("failed to build media for alert %s", alert_id)
            clip_key = thumbnail_key = None

        payload = {
            "type": "behavior_alert",
            "camera_id": self._config.camera_id,
            "alert": {
                "rule": decision.rule,
                "severity": decision.severity,
                "score": decision.score,
                "event_ts": decision.ts,
                "clip_object_key": clip_key,
                "thumbnail_object_key": thumbnail_key,
                "evidence": decision.evidence,
                "frame_count": frame_count,
            },
        }
        try:
            self._redis.publish(WORKER_EVENTS_CHANNEL, json.dumps(payload))
            logger.warning(
                "behavior_alert rule=%s severity=%s score=%.1f clip=%s",
                decision.rule,
                decision.severity,
                decision.score,
                clip_key or "none",
            )
        except redis.RedisError:
            logger.exception("failed to publish alert %s", alert_id)

    def _build_media(self, alert_id, decision, frames):
        camera_id = self._config.camera_id
        clip_key = f"{camera_id}/alerts/{alert_id}.mp4"
        thumbnail_key = f"{camera_id}/alerts/{alert_id}.jpg"

        # Thumbnail : la frame la plus proche de l'événement.
        _, thumbnail_jpeg = min(frames, key=lambda f: abs(f[0] - decision.ts))

        with tempfile.TemporaryDirectory() as tmp:
            clip_path = os.path.join(tmp, "clip.mp4")
            build_clip(frames, self._config.target_fps, clip_path)
            upload_clip(self._s3, self._config.s3_bucket, clip_key, clip_path)

            thumbnail_path = os.path.join(tmp, "thumb.jpg")
            with open(thumbnail_path, "wb") as f:
                f.write(thumbnail_jpeg)
            self._s3.upload_file(
                thumbnail_path,
                self._config.s3_bucket,
                thumbnail_key,
                ExtraArgs={"ContentType": "image/jpeg"},
            )
        return clip_key, thumbnail_key
