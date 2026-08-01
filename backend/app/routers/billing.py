import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import record_audit
from ..billing import (
    apply_webhook_event,
    billing_configured,
    camera_limit_for,
    create_checkout_session,
    parse_webhook_event,
    price_id_for,
    tenant_camera_count,
)
from ..db import get_session
from ..models import Tenant
from ..schemas import BillingOut, CheckoutIn
from ..security import CurrentUser, get_current_user, require_min_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("", response_model=BillingOut)
async def billing_overview(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    tenant = await session.get(Tenant, user.tenant_id)
    return BillingOut(
        plan=tenant.plan,
        subscription_status=tenant.subscription_status,
        camera_count=await tenant_camera_count(session, tenant.id),
        camera_limit=camera_limit_for(tenant.plan),
        configured=billing_configured(),
    )


@router.post("/checkout-session")
async def checkout_session(
    payload: CheckoutIn,
    user: CurrentUser = Depends(require_min_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not billing_configured():
        raise HTTPException(status_code=503, detail="Billing is not configured")
    if not price_id_for(payload.plan):
        raise HTTPException(
            status_code=503, detail=f"No Stripe price configured for {payload.plan}"
        )
    tenant = await session.get(Tenant, user.tenant_id)
    try:
        url = create_checkout_session(tenant, payload.plan, user.email)
    except Exception as exc:
        logger.exception("stripe checkout failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}")
    await session.commit()  # persiste stripe_customer_id si créé
    await record_audit(
        session, user.tenant_id, user.id, "checkout_started", payload.plan
    )
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Webhook Stripe — authentifié par signature, pas par JWT."""
    payload = await request.body()
    try:
        event = parse_webhook_event(payload, stripe_signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    action = await apply_webhook_event(session, event)
    return {"received": True, "action": action}
