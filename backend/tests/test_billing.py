from app.events import handle_worker_event

from .conftest import create_camera, register


async def test_billing_overview_and_camera_limit(client):
    camera, auth = await create_camera(client)

    billing = (await client.get("/billing", headers=auth["headers"])).json()
    assert billing["plan"] == "starter"
    assert billing["camera_limit"] == 2
    assert billing["camera_count"] == 1
    assert billing["configured"] is False

    # Le plan starter autorise 2 caméras : la 3e est refusée (402).
    store = (await client.get("/stores", headers=auth["headers"])).json()[0]
    second = await client.post(
        "/cameras",
        json={"store_id": store["id"], "name": "Cam 2", "rtsp_url": "rtsp://c/2"},
        headers=auth["headers"],
    )
    assert second.status_code == 201
    third = await client.post(
        "/cameras",
        json={"store_id": store["id"], "name": "Cam 3", "rtsp_url": "rtsp://c/3"},
        headers=auth["headers"],
    )
    assert third.status_code == 402
    assert "Upgrade" in third.json()["detail"]


async def test_checkout_unavailable_without_stripe_config(client):
    auth = await register(client)
    response = await client.post(
        "/billing/checkout-session", json={"plan": "pro"}, headers=auth["headers"]
    )
    assert response.status_code == 503


async def test_checkout_session_flow_with_stripe_mocked(client, monkeypatch):
    auth = await register(client)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    from app import billing as billing_module
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        billing_module,
        "create_checkout_session",
        lambda tenant, plan, email: f"https://checkout.stripe.com/test/{plan}",
    )
    monkeypatch.setattr(
        "app.routers.billing.create_checkout_session",
        lambda tenant, plan, email: f"https://checkout.stripe.com/test/{plan}",
    )
    monkeypatch.setattr("app.routers.billing.price_id_for", lambda plan: "price_x")

    response = await client.post(
        "/billing/checkout-session", json={"plan": "pro"}, headers=auth["headers"]
    )
    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.com/test/pro"
    get_settings.cache_clear()


async def test_webhook_checkout_completed_upgrades_plan(client, monkeypatch):
    auth = await register(client)
    tenant = (await client.get("/tenant", headers=auth["headers"])).json()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant["id"], "plan": "pro"},
                "subscription": "sub_123",
                "customer": "cus_123",
            }
        },
    }
    monkeypatch.setattr(
        "app.routers.billing.parse_webhook_event", lambda payload, sig: event
    )

    response = await client.post("/billing/webhook", content=b"{}")
    assert response.status_code == 200
    assert response.json()["action"] == "plan set to pro"

    billing = (await client.get("/billing", headers=auth["headers"])).json()
    assert billing["plan"] == "pro"
    assert billing["camera_limit"] == 10
    assert billing["subscription_status"] == "active"


async def test_webhook_subscription_deleted_downgrades(client, monkeypatch):
    auth = await register(client)
    tenant = (await client.get("/tenant", headers=auth["headers"])).json()

    completed = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant["id"], "plan": "business"},
                "subscription": "sub_9",
                "customer": "cus_9",
            }
        },
    }
    deleted = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_9"}},
    }
    events = iter([completed, deleted])
    monkeypatch.setattr(
        "app.routers.billing.parse_webhook_event",
        lambda payload, sig: next(events),
    )

    await client.post("/billing/webhook", content=b"{}")
    await client.post("/billing/webhook", content=b"{}")

    billing = (await client.get("/billing", headers=auth["headers"])).json()
    assert billing["plan"] == "starter"
    assert billing["subscription_status"] == "canceled"


async def test_webhook_rejects_bad_signature(client, monkeypatch):
    def boom(payload, sig):
        raise ValueError("bad signature")

    monkeypatch.setattr("app.routers.billing.parse_webhook_event", boom)
    response = await client.post("/billing/webhook", content=b"{}")
    assert response.status_code == 400


async def test_higher_plan_raises_camera_limit(client, db_sessionmaker, monkeypatch):
    camera, auth = await create_camera(client)
    tenant = (await client.get("/tenant", headers=auth["headers"])).json()

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant["id"], "plan": "pro"},
                "subscription": "sub_1",
                "customer": "cus_1",
            }
        },
    }
    monkeypatch.setattr(
        "app.routers.billing.parse_webhook_event", lambda payload, sig: event
    )
    await client.post("/billing/webhook", content=b"{}")

    store = (await client.get("/stores", headers=auth["headers"])).json()[0]
    for index in range(2, 5):  # 3 caméras de plus : ok en plan pro
        response = await client.post(
            "/cameras",
            json={
                "store_id": store["id"],
                "name": f"Cam {index}",
                "rtsp_url": f"rtsp://c/{index}",
            },
            headers=auth["headers"],
        )
        assert response.status_code == 201
