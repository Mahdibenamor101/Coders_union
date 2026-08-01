"""Droits RGPD (SPEC §2) : export des données, effacement, journal d'audit."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import record_audit
from ..db import get_session
from ..models import Alert, AuditLog, Camera, Clip, Invitation, Store, Tenant, User
from ..s3 import delete_object
from ..security import CurrentUser, require_min_role

router = APIRouter(tags=["gdpr"])


def _serialize(row, exclude: set[str] = frozenset()) -> dict:
    return {
        column.name: (
            value.isoformat() if hasattr(value := getattr(row, column.name), "isoformat") else value
        )
        for column in row.__table__.columns
        if column.name not in exclude
    }


async def _tenant_rows(session: AsyncSession, tenant_id: str):
    stores = (
        (await session.execute(select(Store).where(Store.tenant_id == tenant_id)))
        .scalars()
        .all()
    )
    store_ids = [store.id for store in stores]
    cameras = (
        (await session.execute(select(Camera).where(Camera.store_id.in_(store_ids))))
        .scalars()
        .all()
        if store_ids
        else []
    )
    camera_ids = [camera.id for camera in cameras]
    clips = (
        (await session.execute(select(Clip).where(Clip.camera_id.in_(camera_ids))))
        .scalars()
        .all()
        if camera_ids
        else []
    )
    alerts = (
        (await session.execute(select(Alert).where(Alert.camera_id.in_(camera_ids))))
        .scalars()
        .all()
        if camera_ids
        else []
    )
    return stores, cameras, clips, alerts


@router.get("/export")
async def export_tenant_data(
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Droit d'accès : export JSON de toutes les données du tenant.

    Les URLs RTSP chiffrées et les hash de mots de passe sont exclus.
    """
    tenant = await session.get(Tenant, user.tenant_id)
    users = (
        (await session.execute(select(User).where(User.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    stores, cameras, clips, alerts = await _tenant_rows(session, tenant.id)
    logs = (
        (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant.id)
                .order_by(AuditLog.created_at)
            )
        )
        .scalars()
        .all()
    )
    await record_audit(session, tenant.id, user.id, "data_export")
    return {
        "tenant": _serialize(tenant, exclude={"stripe_customer_id", "stripe_subscription_id"}),
        "users": [_serialize(u, exclude={"password_hash"}) for u in users],
        "stores": [_serialize(s) for s in stores],
        "cameras": [_serialize(c, exclude={"rtsp_url_encrypted"}) for c in cameras],
        "clips": [_serialize(c) for c in clips],
        "alerts": [_serialize(a) for a in alerts],
        "audit_logs": [_serialize(entry) for entry in logs],
    }


@router.delete("/tenant/data", status_code=204)
async def delete_tenant_data(
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    """Droit à l'effacement : supprime tout le tenant (base + médias S3)."""
    tenant = await session.get(Tenant, user.tenant_id)
    _stores, cameras, clips, alerts = await _tenant_rows(session, tenant.id)

    for clip in clips:
        if clip.object_key:
            delete_object(clip.object_key)
    for alert in alerts:
        for key in (alert.clip_object_key, alert.thumbnail_object_key):
            if key:
                delete_object(key)
    for camera in cameras:
        delete_object(f"{camera.id}/snapshot.jpg")

    # La suppression du tenant cascade sur users, stores, caméras, clips,
    # alertes, invitations et journal d'audit.
    await session.delete(tenant)
    await session.commit()


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 200,
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 1000))
    )
    return [_serialize(entry) for entry in result.scalars().all()]
