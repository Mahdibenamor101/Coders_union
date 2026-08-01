from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # Le tenant est celui de l'utilisateur connecté — jamais fourni par le client.
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


ZoneType = Literal["rayon", "caisse", "entree", "sortie", "reserve", "autre"]


class ZoneIn(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    type: ZoneType
    # Polygone en coordonnées normalisées [0,1] sur l'image caméra.
    polygon: list[tuple[float, float]] = Field(min_length=3)

    @field_validator("polygon")
    @classmethod
    def coordinates_in_unit_range(cls, polygon):
        for x, y in polygon:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("polygon coordinates must be normalized in [0, 1]")
        return polygon


class ZoneOut(ZoneIn):
    id: str


class ZonesUpdate(BaseModel):
    zones: list[ZoneIn]


class CameraSettingsIn(BaseModel):
    """Seuils du moteur de règles, par caméra (tous optionnels — voir SPEC §6)."""

    model_config = ConfigDict(extra="forbid")

    alert_threshold: float | None = Field(default=None, gt=0)
    cooldown_seconds: float | None = Field(default=None, ge=0)
    window_seconds: float | None = Field(default=None, gt=0)
    dwell_seconds: float | None = Field(default=None, gt=0)
    low_motion_radius: float | None = Field(default=None, ge=0, le=1)
    min_shelf_seconds: float | None = Field(default=None, ge=0)
    checkout_min_seconds: float | None = Field(default=None, ge=0)


AlertStatus = Literal["pending", "confirmed", "false_positive", "dismissed"]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    camera_id: str
    rule: str
    severity: str
    score: float
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    event_ts: datetime
    clip_object_key: str | None
    thumbnail_object_key: str | None
    evidence: list
    created_at: datetime


class AlertReviewIn(BaseModel):
    # reviewed_by est l'utilisateur connecté, déterminé côté serveur.
    status: AlertStatus


UserRole = Literal["admin", "manager", "viewer"]


class RegisterIn(BaseModel):
    """Onboarding : crée l'organisation (tenant) et son premier admin."""

    company_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255, pattern=r"^\S+@\S+\.\S+$")
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=255)


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    role: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255, pattern=r"^\S+@\S+\.\S+$")
    role: UserRole = "viewer"


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InvitationAcceptIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=255)


class TenantUpdateMe(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    retention_days: int | None = Field(default=None, ge=1, le=90)


class CheckoutIn(BaseModel):
    plan: Literal["pro", "business"]


class BillingOut(BaseModel):
    plan: str
    subscription_status: str
    camera_count: int
    camera_limit: int
    configured: bool


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
