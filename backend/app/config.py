from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/surveillance"
    redis_url: str = "redis://redis:6379/0"

    # Phase 1 : une seule clé API partagée (header X-API-Key). Auth complète en Phase 5.
    api_key: str
    # Clé Fernet pour chiffrer les URLs RTSP au repos (elles contiennent des identifiants).
    fernet_key: str

    s3_endpoint_url: str = "http://minio:9000"
    # Endpoint vu depuis l'extérieur du réseau Docker, utilisé pour les URLs présignées.
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "clips"

    clip_pre_seconds: int = 20
    clip_post_seconds: int = 20

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
