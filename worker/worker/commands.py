import json
import logging
import os
import tempfile
import threading
import time

import redis

from .clip_extractor import build_clip, upload_clip
from .config import WorkerConfig
from .ring_buffer import FrameRingBuffer

logger = logging.getLogger(__name__)

WORKER_EVENTS_CHANNEL = "worker_events"


class CommandListener(threading.Thread):
    """Écoute `camera_commands:{camera_id}` sur Redis et traite les extractions de clips."""

    def __init__(
        self,
        config: WorkerConfig,
        buffer: FrameRingBuffer,
        s3,
        on_update_zones=None,
    ):
        super().__init__(daemon=True, name="command-listener")
        self._config = config
        self._buffer = buffer
        self._s3 = s3
        self._on_update_zones = on_update_zones
        self._redis = redis.Redis.from_url(config.redis_url)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        pubsub = self._redis.pubsub()
        channel = f"camera_commands:{self._config.camera_id}"
        pubsub.subscribe(channel)
        logger.info("listening for commands on %r", channel)
        while not self._stop.is_set():
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            try:
                command = json.loads(message["data"])
            except (ValueError, TypeError):
                logger.warning("ignoring malformed command: %r", message["data"])
                continue
            action = command.get("action")
            if action == "extract_clip":
                threading.Thread(
                    target=self._extract_clip, args=(command,), daemon=True
                ).start()
            elif action == "update_zones" and self._on_update_zones is not None:
                try:
                    self._on_update_zones(command.get("zones", []))
                    logger.info("zones updated (%d zones)", len(command.get("zones", [])))
                except Exception:
                    logger.exception("failed to apply zone update")

    def _extract_clip(self, command: dict) -> None:
        clip_id = command["clip_id"]
        event_ts = float(command.get("event_ts") or time.time())
        pre = float(command.get("pre_seconds", 20))
        post = float(command.get("post_seconds", 20))

        # On attend la fin de la fenêtre « après » pour capter les frames post-événement.
        remaining = event_ts + post - time.time()
        if remaining > 0:
            time.sleep(remaining)

        try:
            frames = self._buffer.snapshot(event_ts - pre, event_ts + post)
            if not frames:
                raise RuntimeError("no frames available in buffer for requested window")
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, f"{clip_id}.mp4")
                duration = build_clip(frames, self._config.target_fps, path)
                key = f"{self._config.camera_id}/{clip_id}.mp4"
                upload_clip(self._s3, self._config.s3_bucket, key, path)
            self._publish(
                {
                    "type": "clip_ready",
                    "clip_id": clip_id,
                    "object_key": key,
                    "duration_seconds": duration,
                    "frame_count": len(frames),
                }
            )
            logger.info("clip %s ready (%d frames)", clip_id, len(frames))
        except Exception as exc:
            logger.exception("clip %s failed", clip_id)
            self._publish({"type": "clip_failed", "clip_id": clip_id, "error": str(exc)})

    def _publish(self, payload: dict) -> None:
        self._redis.publish(WORKER_EVENTS_CHANNEL, json.dumps(payload))
