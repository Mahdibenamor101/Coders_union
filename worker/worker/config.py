import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerConfig:
    camera_id: str
    api_url: str
    api_key: str
    redis_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    target_fps: float
    buffer_seconds: float
    jpeg_quality: int
    analysis_enabled: bool
    yolo_model: str
    analysis_fps: float
    dwell_seconds: float
    track_ttl_seconds: float
    objects_enabled: bool
    object_model: str
    object_every_n: int
    object_confidence: float
    alert_clip_pre_seconds: float
    alert_clip_post_seconds: float
    verification_enabled: bool
    verification_model: str


def load_config() -> WorkerConfig:
    def required(name: str) -> str:
        value = os.environ.get(name, "")
        if not value:
            raise RuntimeError(f"missing required environment variable: {name}")
        return value

    return WorkerConfig(
        camera_id=required("CAMERA_ID"),
        api_url=os.environ.get("API_URL", "http://api:8000").rstrip("/"),
        api_key=required("API_KEY"),
        redis_url=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        s3_endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://minio:9000"),
        s3_access_key=required("S3_ACCESS_KEY"),
        s3_secret_key=required("S3_SECRET_KEY"),
        s3_bucket=os.environ.get("S3_BUCKET", "clips"),
        target_fps=float(os.environ.get("TARGET_FPS", "8")),
        buffer_seconds=float(os.environ.get("BUFFER_SECONDS", "60")),
        jpeg_quality=int(os.environ.get("JPEG_QUALITY", "80")),
        analysis_enabled=os.environ.get("ANALYSIS_ENABLED", "true").lower()
        in ("1", "true", "yes"),
        yolo_model=os.environ.get("YOLO_MODEL", "yolov8n-pose.pt"),
        analysis_fps=float(os.environ.get("ANALYSIS_FPS", "5")),
        dwell_seconds=float(os.environ.get("DWELL_SECONDS", "30")),
        track_ttl_seconds=float(os.environ.get("TRACK_TTL_SECONDS", "5")),
        objects_enabled=os.environ.get("OBJECTS_ENABLED", "true").lower()
        in ("1", "true", "yes"),
        object_model=os.environ.get("OBJECT_MODEL", "yolov8n.pt"),
        object_every_n=int(os.environ.get("OBJECT_EVERY_N", "2")),
        object_confidence=float(os.environ.get("OBJECT_CONFIDENCE", "0.35")),
        alert_clip_pre_seconds=float(os.environ.get("ALERT_CLIP_PRE_SECONDS", "20")),
        alert_clip_post_seconds=float(os.environ.get("ALERT_CLIP_POST_SECONDS", "20")),
        # L'étape multimodale requiert ANTHROPIC_API_KEY ; désactivable par tenant.
        verification_enabled=os.environ.get("VERIFICATION_ENABLED", "true").lower()
        in ("1", "true", "yes")
        and bool(os.environ.get("ANTHROPIC_API_KEY")),
        verification_model=os.environ.get("VERIFICATION_MODEL", "claude-opus-5"),
    )
