from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plan: str = "starter"
    retention_days: int = Field(default=30, ge=1, le=90)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: str | None = None
    retention_days: int | None = Field(default=None, ge=1, le=90)


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    plan: str
    retention_days: int
    created_at: datetime


class StoreCreate(BaseModel):
    tenant_id: str
    name: str = Field(min_length=1, max_length=255)
    address: str = ""
    timezone: str = "UTC"


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = None
    timezone: str | None = None


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    name: str
    address: str
    timezone: str
    created_at: datetime


class CameraCreate(BaseModel):
    store_id: str
    name: str = Field(min_length=1, max_length=255)
    rtsp_url: str = Field(min_length=1)


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    rtsp_url: str | None = None
    status: str | None = None


# Ne contient jamais l'URL RTSP (identifiants) — voir /cameras/{id}/stream-url.
class CameraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    store_id: str
    name: str
    status: str
    last_seen_at: datetime | None
    zones: list
    created_at: datetime


class StreamUrlOut(BaseModel):
    rtsp_url: str


class ClipRequest(BaseModel):
    # Timestamp Unix de l'événement ; défaut = maintenant.
    event_ts: float | None = None


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    camera_id: str
    status: str
    object_key: str | None
    duration_seconds: float | None
    error: str | None
    requested_at: datetime
    created_at: datetime


class ClipUrlOut(BaseModel):
    url: str
    expires_in: int
