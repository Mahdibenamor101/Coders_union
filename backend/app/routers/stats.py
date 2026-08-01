from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Alert

router = APIRouter(prefix="/stats", tags=["stats"])

REVIEWED_STATUSES = ("confirmed", "false_positive", "dismissed")


@router.get("/alerts-per-day")
async def alerts_per_day(
    days: int = 14, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    days = max(1, min(days, 90))
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=days - 1)

    result = await session.execute(
        select(func.date(Alert.created_at), func.count())
        .where(Alert.created_at >= datetime.combine(since, datetime.min.time(), timezone.utc))
        .group_by(func.date(Alert.created_at))
    )
    counts = {str(day): count for day, count in result.all()}
    return [
        {"date": str(since + timedelta(days=offset)),
         "count": counts.get(str(since + timedelta(days=offset)), 0)}
        for offset in range(days)
    ]


@router.get("/rules")
async def rule_stats(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Par règle : volumes par statut de revue et taux de faux positifs.

    Le taux de faux positifs (faux positifs / alertes revues) est l'indicateur
    qui guide l'ajustement des seuils par caméra (SPEC §7 Phase 4).
    """
    result = await session.execute(
        select(Alert.rule, Alert.status, func.count()).group_by(
            Alert.rule, Alert.status
        )
    )
    rules: dict[str, dict] = {}
    for rule, status, count in result.all():
        entry = rules.setdefault(
            rule,
            {"rule": rule, "total": 0, "pending": 0, "confirmed": 0,
             "false_positive": 0, "dismissed": 0, "false_positive_rate": None},
        )
        entry["total"] += count
        if status in entry:
            entry[status] += count

    for entry in rules.values():
        reviewed = sum(entry[status] for status in REVIEWED_STATUSES)
        if reviewed:
            entry["false_positive_rate"] = round(
                entry["false_positive"] / reviewed, 3
            )
    return sorted(rules.values(), key=lambda e: e["total"], reverse=True)
