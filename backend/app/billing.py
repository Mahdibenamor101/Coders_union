"""Facturation Stripe : plans par nombre de caméras (SPEC §7 Phase 5).

Sans clé Stripe configurée, la facturation est désactivée : tout le monde reste
sur le plan `starter` et les endpoints de checkout renvoient 503.
"""

import logging

import stripe
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import Camera, Store, Tenant

logger = logging.getLogger(__name__)

PLAN_CAMERA_LIMITS = {"starter": 2, "pro": 10, "business": 50}


def camera_limit_for(plan: str) -> int:
    return PLAN_CAMERA_LIMITS.get(plan, PLAN_CAMERA_LIMITS["starter"])


def billing_configured() -> bool:
    return bool(get_settings().stripe_secret_key)


def price_id_for(plan: str) -> str | None:
    settings = get_settings()
    return {
        "pro": settings.stripe_price_pro,
        "business": settings.stripe_price_business,
    }.get(plan) or None


async def tenant_camera_count(session: AsyncSession, tenant_id: str) -> int:
    result = await session.execute(
        select(func.count(Camera.id))
        .join(Store, Camera.store_id == Store.id)
        .where(Store.tenant_id == tenant_id)
    )
    return result.scalar_one()


def create_checkout_session(tenant: Tenant, plan: str, email: str) -> str:
    """Crée la session Stripe Checkout et retourne son URL."""
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    if not tenant.stripe_customer_id:
        customer = stripe.Customer.create(
            email=email, name=tenant.name, metadata={"tenant_id": tenant.id}
        )
        tenant.stripe_customer_id = customer["id"]

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=tenant.stripe_customer_id,
        line_items=[{"price": price_id_for(plan), "quantity": 1}],
        success_url=f"{settings.frontend_url}/billing?checkout=success",
        cancel_url=f"{settings.frontend_url}/billing?checkout=cancelled",
        metadata={"tenant_id": tenant.id, "plan": plan},
    )
    return session["url"]


def parse_webhook_event(payload: bytes, signature: str) -> dict:
    settings = get_settings()
    return stripe.Webhook.construct_event(
        payload, signature, settings.stripe_webhook_secret
    )


async def apply_webhook_event(session: AsyncSession, event: dict) -> str:
    """Applique un événement Stripe au tenant concerné. Retourne l'action faite."""
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        plan = data.get("metadata", {}).get("plan", "pro")
        tenant = await session.get(Tenant, tenant_id) if tenant_id else None
        if tenant is None:
            logger.warning("checkout completed for unknown tenant: %s", tenant_id)
            return "ignored"
        tenant.plan = plan
        tenant.subscription_status = "active"
        tenant.stripe_subscription_id = data.get("subscription")
        if data.get("customer"):
            tenant.stripe_customer_id = data["customer"]
        await session.commit()
        return f"plan set to {plan}"

    if event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        customer_id = data.get("customer")
        result = await session.execute(
            select(Tenant).where(Tenant.stripe_customer_id == customer_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant is None:
            logger.warning("subscription event for unknown customer: %s", customer_id)
            return "ignored"
        if event_type == "customer.subscription.deleted":
            tenant.plan = "starter"
            tenant.subscription_status = "canceled"
            tenant.stripe_subscription_id = None
        else:
            tenant.subscription_status = data.get("status", "active")
        await session.commit()
        return "subscription updated"

    return "ignored"
