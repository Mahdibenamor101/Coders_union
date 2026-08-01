from app.events import ALERTS_FEED_CHANNEL, handle_worker_event
from app.models import Alert

from .conftest import create_camera


def behavior_alert_payload(camera_id, rule="dissimulation", severity="high", score=80.0):
    return {
        "type": "behavior_alert",
        "camera_id": camera_id,
        "alert": {
            "rule": rule,
            "severity": severity,
            "score": score,
            "event_ts": 1000.0,
            "clip_object_key": f"{camera_id}/alerts/a1.mp4",
            "thumbnail_object_key": f"{camera_id}/alerts/a1.jpg",
            "evidence": [{"stage": "grab", "score": 15.0}],
        },
    }


async def store_alert(client, db_sessionmaker, auth=None, **kwargs):
    camera, auth = await create_camera(client, auth=auth)
    async with db_sessionmaker() as session:
        broadcasts = await handle_worker_event(
            session, behavior_alert_payload(camera["id"], **kwargs)
        )
    return camera, auth, broadcasts


async def test_behavior_alert_creates_row_and_broadcast(client, db_sessionmaker):
    camera, auth, broadcasts = await store_alert(client, db_sessionmaker)

    listed = (await client.get("/alerts", headers=auth["headers"])).json()
    assert len(listed) == 1
    alert = listed[0]
    assert alert["camera_id"] == camera["id"]
    assert alert["rule"] == "dissimulation"
    assert alert["status"] == "pending"

    assert len(broadcasts) == 1
    channel, message = broadcasts[0]
    assert channel == ALERTS_FEED_CHANNEL
    assert message["type"] == "alert_created"
    assert message["alert_id"] == alert["id"]
    # Le broadcast porte le tenant pour le filtrage WebSocket.
    tenant = (await client.get("/tenant", headers=auth["headers"])).json()
    assert message["tenant_id"] == tenant["id"]


async def test_alert_for_unknown_camera_is_ignored(db_sessionmaker):
    async with db_sessionmaker() as session:
        broadcasts = await handle_worker_event(
            session, behavior_alert_payload("missing-camera")
        )
        assert broadcasts == []
        assert (await session.get(Alert, "anything")) is None


async def test_review_workflow_records_current_user(client, db_sessionmaker):
    _camera, auth, _ = await store_alert(client, db_sessionmaker)
    alert = (await client.get("/alerts", headers=auth["headers"])).json()[0]

    reviewed = (
        await client.post(
            f"/alerts/{alert['id']}/review",
            json={"status": "false_positive"},
            headers=auth["headers"],
        )
    ).json()
    assert reviewed["status"] == "false_positive"
    # reviewed_by = l'utilisateur connecté, déterminé côté serveur.
    assert reviewed["reviewed_by"] == auth["email"]
    assert reviewed["reviewed_at"] is not None

    reset = (
        await client.post(
            f"/alerts/{alert['id']}/review",
            json={"status": "pending"},
            headers=auth["headers"],
        )
    ).json()
    assert reset["reviewed_by"] is None

    bad = await client.post(
        f"/alerts/{alert['id']}/review",
        json={"status": "voleur"},
        headers=auth["headers"],
    )
    assert bad.status_code == 422


async def test_alert_manual_deletion(client, db_sessionmaker, monkeypatch):
    deleted_keys = []
    monkeypatch.setattr("app.routers.alerts.delete_object", deleted_keys.append)

    _camera, auth, _ = await store_alert(client, db_sessionmaker)
    alert = (await client.get("/alerts", headers=auth["headers"])).json()[0]

    response = await client.delete(
        f"/alerts/{alert['id']}", headers=auth["headers"]
    )
    assert response.status_code == 204
    assert (await client.get("/alerts", headers=auth["headers"])).json() == []
    # Les médias S3 sont supprimés aussi (RGPD).
    assert len(deleted_keys) == 2


async def test_media_urls_conflict_when_missing(client, db_sessionmaker):
    camera, auth = await create_camera(client)
    payload = behavior_alert_payload(camera["id"])
    payload["alert"]["clip_object_key"] = None
    payload["alert"]["thumbnail_object_key"] = None
    async with db_sessionmaker() as session:
        await handle_worker_event(session, payload)

    alert = (await client.get("/alerts", headers=auth["headers"])).json()[0]
    assert (
        await client.get(f"/alerts/{alert['id']}/clip-url", headers=auth["headers"])
    ).status_code == 409
