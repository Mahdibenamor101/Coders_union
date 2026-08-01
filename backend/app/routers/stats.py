from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Alert, Camera, Store
from ..security import CurrentUser, get_current_user

router = APIRouter(prefix="/stats", tags=["stats"])

REVIEWED_STATUSES = ("confirmed", "false_positive", "dismissed")


def _tenant_alerts(tenant_id: str):
    return (
        select(Alert)
        .join(Camera, Alert.camera_id == Camera.id)
        .join(Store, Camera.store_id == Store.id)
        .where(Store.tenant_id == tenant_id)
    )


@router.get("/alerts-per-day")
async def alerts_per_day(
    days: int = 14,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    days = max(1, min(days, 90))
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=days - 1)

    result = await session.execute(
        select(func.date(Alert.created_at), func.count())
        .select_from(Alert)
        .join(Camera, Alert.camera_id == Camera.id)
        .join(Store, Camera.store_id == Store.id)
        .where(
            Store.tenant_id == user.tenant_id,
            Alert.created_at
            >= datetime.combine(since, datetime.min.time(), timezone.utc),
        )
        .group_by(func.date(Alert.created_at))
    )
    counts = {str(day): count for day, count in result.all()}
    return [
        {
            "date": str(since + timedelta(days=offset)),
            "count": counts.get(str(since + timedelta(days=offset)), 0),
        }
        for offset in range(days)
    ]


@router.get("/rules")
async def rule_stats(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Par règle : volumes par statut de revue et taux de faux positifs."""
    result = await session.execute(
        select(Alert.rule, Alert.status, func.count())
        .select_from(Alert)
        .join(Camera, Alert.camera_id == Camera.id)
        .join(Store, Camera.store_id == Store.id)
        .where(Store.tenant_id == user.tenant_id)
        .group_by(Alert.rule, Alert.status)
    )
    rules: dict[str, dict] = {}
    for rule, status, count in result.all():
        entry = rules.setdefault(
            rule,
            {
                "rule": rule,
                "total": 0,
                "pending": 0,
                "confirmed": 0,
                "false_positive": 0,
                "dismissed": 0,
                "false_positive_rate": None,
            },
        )
        entry["total"] += count
        if status in entry:
            entry[status] += count

    for entry in rules.values():
        reviewed = sum(entry[status] for status in REVIEWED_STATUSES)
        if reviewed:
            entry["false_positive_rate"] = round(entry["false_positive"] / reviewed, 3)
    return sorted(rules.values(), key=lambda e: e["total"], reverse=True)
