import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(50), default="starter")
    # RGPD : rétention des clips en jours (30 par défaut, 90 max — validé côté schéma).
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stores: Mapped[list["Store"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tenant: Mapped[Tenant] = relationship(back_populates="stores")
    cameras: Mapped[list["Camera"]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    # L'URL RTSP contient des identifiants : chiffrée Fernet, jamais renvoyée par l'API
    # publique (seul /cameras/{id}/stream-url la déchiffre, pour les workers).
    rtsp_url_encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="offline")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Polygones de zones (rayon, caisse, entrée/sortie…) — utilisés à partir de la Phase 2.
    zones: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    store: Mapped[Store] = relationship(back_populates="cameras")
    clips: Mapped[list["Clip"]] = relationship(
        back_populates="camera", cascade="all, delete-orphan"
    )


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    object_key: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    # Timestamp de l'événement autour duquel le clip est découpé (20 s avant/après).
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    camera: Mapped[Camera] = relationship(back_populates="clips")
