from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


async def record_audit(
    session: AsyncSession,
    tenant_id: str,
    user_id: str | None,
    action: str,
    target: str = "",
) -> None:
    """Trace une action (RGPD §2 : notamment chaque visionnage de clip)."""
    session.add(
        AuditLog(tenant_id=tenant_id, user_id=user_id, action=action, target=target)
    )
    await session.commit()
