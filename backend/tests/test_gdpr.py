from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.events import handle_worker_event
from app.models import Alert, Clip, Tenant, User
from app.retention import run_retention_cleanup

from .conftest import create_camera, register
from .test_alerts import behavior_alert_payload


async def test_clip_viewing_is_audited(client, db_sessionmaker):
    camera, auth = await create_camera(client)
    async with db_sessionmaker() as session:
        await handle_worker_event(session, behavior_alert_payload(camera["id"]))

    alert = (await client.get("/alerts", headers=auth["headers"])).json()[0]
    response = await client.get(
        f"/alerts/{alert['id']}/clip-url", headers=auth["headers"]
    )
    assert response.status_code == 200

    logs = (await client.get("/audit-logs", headers=auth["headers"])).json()
    viewed = [log for log in logs if log["action"] == "clip_viewed"]
    assert len(viewed) == 1
    assert viewed[0]["target"] == alert["id"]
    assert viewed[0]["user_id"] is not None


async def test_export_contains_all_tenant_data_without_secrets(
    client, db_sessionmaker
):
    camera, auth = await create_camera(client)
    async with db_sessionmaker() as session:
        await handle_worker_event(session, behavior_alert_payload(camera["id"]))

    export = (await client.get("/export", headers=auth["headers"])).json()
    assert export["tenant"]["name"] == "Boutique SARL"
    assert len(export["users"]) == 1
    assert len(export["cameras"]) == 1
    assert len(export["alerts"]) == 1

    # Jamais de secrets dans l'export.
    assert "password_hash" not in export["users"][0]
    assert "rtsp_url_encrypted" not in export["cameras"][0]

    # L'export lui-même est audité.
    logs = (await client.get("/audit-logs", headers=auth["headers"])).json()
    assert any(log["action"] == "data_export" for log in logs)


async def test_tenant_deletion_erases_everything(client, db_sessionmaker, monkeypatch):
    deleted_keys = []
    monkeypatch.setattr("app.routers.gdpr.delete_object", deleted_keys.append)

    camera, auth = await create_camera(client)
    async with db_sessionmaker() as session:
        await handle_worker_event(session, behavior_alert_payload(camera["id"]))

    response = await client.delete("/tenant/data", headers=auth["headers"])
    assert response.status_code == 204

    # Médias supprimés : clip + thumbnail de l'alerte + snapshot caméra.
    assert len(deleted_keys) == 3

    # Plus rien en base pour ce tenant, et le token ne fonctionne plus.
    async with db_sessionmaker() as session:
        assert (await session.execute(select(Tenant))).scalars().all() == []
        assert (await session.execute(select(User))).scalars().all() == []
        assert (await session.execute(select(Alert))).scalars().all() == []
    assert (await client.get("/auth/me", headers=auth["headers"])).status_code == 401


async def test_retention_cleanup_deletes_only_expired(client, db_sessionmaker):
    camera, auth = await create_camera(client)
    async with db_sessionmaker() as session:
        await handle_worker_event(session, behavior_alert_payload(camera["id"]))

    clip = (
        await client.post(
            f"/cameras/{camera['id']}/clip", json={}, headers=auth["headers"]
        )
    ).json()

    deleted_keys = []
    # Rien n'a dépassé la rétention (30 j) : aucune suppression.
    async with db_sessionmaker() as session:
        counts = await run_retention_cleanup(session, delete_media=deleted_keys.append)
    assert counts == {"clips": 0, "alerts": 0}

    # On vieillit artificiellement les données au-delà de la rétention.
    old = datetime.now(timezone.utc) - timedelta(days=31)
    async with db_sessionmaker() as session:
        for row in (await session.execute(select(Alert))).scalars().all():
            row.created_at = old
        for row in (await session.execute(select(Clip))).scalars().all():
            row.created_at = old
            row.object_key = "some/clip.mp4"
        await session.commit()

    async with db_sessionmaker() as session:
        counts = await run_retention_cleanup(session, delete_media=deleted_keys.append)
    assert counts == {"clips": 1, "alerts": 1}
    # Médias purgés : clip demandé + clip et thumbnail de l'alerte.
    assert len(deleted_keys) == 3

    assert (await client.get("/alerts", headers=auth["headers"])).json() == []


async def test_retention_respects_per_tenant_setting(client, db_sessionmaker):
    camera, auth = await create_camera(client)
    # Ce tenant réduit sa rétention à 1 jour.
    await client.patch(
        "/tenant", json={"retention_days": 1}, headers=auth["headers"]
    )
    async with db_sessionmaker() as session:
        await handle_worker_event(session, behavior_alert_payload(camera["id"]))

    old = datetime.now(timezone.utc) - timedelta(days=2)
    async with db_sessionmaker() as session:
        for row in (await session.execute(select(Alert))).scalars().all():
            row.created_at = old
        await session.commit()

    async with db_sessionmaker() as session:
        counts = await run_retention_cleanup(session, delete_media=lambda key: None)
    assert counts["alerts"] == 1
