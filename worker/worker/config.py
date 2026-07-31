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
    )
