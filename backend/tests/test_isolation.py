"""Critère de fin de Phase 5 (SPEC §7) : deux tenants distincts ne voient
jamais les données l'un de l'autre — vérifié endpoint par endpoint."""

from app.events import handle_worker_event

from .conftest import create_camera, register
from .test_alerts import behavior_alert_payload


async def two_tenants_with_data(client, db_sessionmaker):
    camera_a, auth_a = await create_camera(client, name="Cam A")
    camera_b, auth_b = await create_camera(client, name="Cam B")
    async with db_sessionmaker() as session:
        await handle_worker_event(session, behavior_alert_payload(camera_a["id"]))
        await handle_worker_event(
            session, behavior_alert_payload(camera_b["id"], rule="zone_interdite")
        )
    return (camera_a, auth_a), (camera_b, auth_b)


async def test_lists_are_tenant_scoped(client, db_sessionmaker):
    (camera_a, auth_a), (camera_b, auth_b) = await two_tenants_with_data(
        client, db_sessionmaker
    )

    cameras_a = (await client.get("/cameras", headers=auth_a["headers"])).json()
    cameras_b = (await client.get("/cameras", headers=auth_b["headers"])).json()
    assert [c["id"] for c in cameras_a] == [camera_a["id"]]
    assert [c["id"] for c in cameras_b] == [camera_b["id"]]

    stores_a = (await client.get("/stores", headers=auth_a["headers"])).json()
    stores_b = (await client.get("/stores", headers=auth_b["headers"])).json()
    assert len(stores_a) == 1 and len(stores_b) == 1
    assert stores_a[0]["id"] != stores_b[0]["id"]

    alerts_a = (await client.get("/alerts", headers=auth_a["headers"])).json()
    alerts_b = (await client.get("/alerts", headers=auth_b["headers"])).json()
    assert [a["rule"] for a in alerts_a] == ["dissimulation"]
    assert [a["rule"] for a in alerts_b] == ["zone_interdite"]


async def test_cross_tenant_object_access_is_404(client, db_sessionmaker):
    (camera_a, auth_a), (_camera_b, auth_b) = await two_tenants_with_data(
        client, db_sessionmaker
    )
    alert_a = (await client.get("/alerts", headers=auth_a["headers"])).json()[0]
    store_a = (await client.get("/stores", headers=auth_a["headers"])).json()[0]

    b = auth_b["headers"]
    # B ne peut ni lire ni toucher les objets de A — 404 systématique.
    assert (await client.get(f"/cameras/{camera_a['id']}", headers=b)).status_code == 404
    assert (await client.get(f"/stores/{store_a['id']}", headers=b)).status_code == 404
    assert (await client.get(f"/alerts/{alert_a['id']}", headers=b)).status_code == 404
    assert (
        await client.get(f"/cameras/{camera_a['id']}/zones", headers=b)
    ).status_code == 404
    assert (
        await client.put(
            f"/cameras/{camera_a['id']}/settings",
            json={"alert_threshold": 1},
            headers=b,
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/alerts/{alert_a['id']}/review", json={"status": "confirmed"}, headers=b
        )
    ).status_code == 404
    assert (
        await client.delete(f"/alerts/{alert_a['id']}", headers=b)
    ).status_code == 404
    assert (
        await client.post(f"/cameras/{camera_a['id']}/clip", json={}, headers=b)
    ).status_code == 404
    assert (
        await client.delete(f"/cameras/{camera_a['id']}", headers=b)
    ).status_code == 404
    assert (
        await client.get(f"/alerts/{alert_a['id']}/clip-url", headers=b)
    ).status_code == 404

    # Filtrer sur la caméra d'un autre tenant est aussi un 404.
    assert (
        await client.get(f"/alerts?camera_id={camera_a['id']}", headers=b)
    ).status_code == 404


async def test_stats_are_tenant_scoped(client, db_sessionmaker):
    (_a, auth_a), (_b, auth_b) = await two_tenants_with_data(client, db_sessionmaker)

    rules_a = (await client.get("/stats/rules", headers=auth_a["headers"])).json()
    rules_b = (await client.get("/stats/rules", headers=auth_b["headers"])).json()
    assert [r["rule"] for r in rules_a] == ["dissimulation"]
    assert [r["rule"] for r in rules_b] == ["zone_interdite"]

    days_b = (
        await client.get("/stats/alerts-per-day?days=3", headers=auth_b["headers"])
    ).json()
    assert days_b[-1]["count"] == 1


async def test_clips_are_tenant_scoped(client, db_sessionmaker):
    camera_a, auth_a = await create_camera(client)
    _camera_b, auth_b = await create_camera(client)

    clip = (
        await client.post(
            f"/cameras/{camera_a['id']}/clip", json={}, headers=auth_a["headers"]
        )
    ).json()

    assert (
        await client.get(f"/clips/{clip['id']}", headers=auth_b["headers"])
    ).status_code == 404
    assert (
        await client.get(
            f"/cameras/{camera_a['id']}/clips", headers=auth_b["headers"]
        )
    ).status_code == 404


async def test_users_and_audit_are_tenant_scoped(client, db_sessionmaker):
    auth_a = await register(client)
    auth_b = await register(client)

    users_a = (await client.get("/users", headers=auth_a["headers"])).json()
    users_b = (await client.get("/users", headers=auth_b["headers"])).json()
    assert [u["email"] for u in users_a] == [auth_a["email"]]
    assert [u["email"] for u in users_b] == [auth_b["email"]]

    logs_a = (await client.get("/audit-logs", headers=auth_a["headers"])).json()
    assert all(log["tenant_id"] != "" for log in logs_a)
    emails_in_a = {log["target"] for log in logs_a if log["action"] == "register"}
    assert auth_b["email"] not in emails_in_a
