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


async def store_alert(client, db_sessionmaker, **kwargs):
    camera = await create_camera(client)
    async with db_sessionmaker() as session:
        broadcasts = await handle_worker_event(
            session, behavior_alert_payload(camera["id"], **kwargs)
        )
    return camera, broadcasts


async def test_behavior_alert_creates_row_and_broadcast(client, db_sessionmaker):
    camera, broadcasts = await store_alert(client, db_sessionmaker)

    listed = (await client.get("/alerts")).json()
    assert len(listed) == 1
    alert = listed[0]
    assert alert["camera_id"] == camera["id"]
    assert alert["rule"] == "dissimulation"
    assert alert["severity"] == "high"
    assert alert["score"] == 80.0
    assert alert["status"] == "pending"
    assert alert["evidence"] == [{"stage": "grab", "score": 15.0}]

    assert len(broadcasts) == 1
    channel, message = broadcasts[0]
    assert channel == ALERTS_FEED_CHANNEL
    assert message["type"] == "alert_created"
    assert message["alert_id"] == alert["id"]


async def test_alert_for_unknown_camera_is_ignored(db_sessionmaker):
    async with db_sessionmaker() as session:
        broadcasts = await handle_worker_event(
            session, behavior_alert_payload("missing-camera")
        )
        assert broadcasts == []
        assert (await session.get(Alert, "anything")) is None


async def test_alert_list_filters(client, db_sessionmaker):
    camera, _ = await store_alert(client, db_sessionmaker)
    async with db_sessionmaker() as session:
        await handle_worker_event(
            session,
            behavior_alert_payload(camera["id"], rule="zone_interdite", score=70.0),
        )

    by_rule = (await client.get("/alerts?rule=zone_interdite")).json()
    assert len(by_rule) == 1
    assert by_rule[0]["rule"] == "zone_interdite"

    by_camera = (await client.get(f"/alerts?camera_id={camera['id']}")).json()
    assert len(by_camera) == 2

    assert (await client.get("/alerts?camera_id=unknown")).status_code == 404


async def test_review_workflow(client, db_sessionmaker):
    _, _ = await store_alert(client, db_sessionmaker)
    alert = (await client.get("/alerts")).json()[0]

    reviewed = (
        await client.post(
            f"/alerts/{alert['id']}/review",
            json={"status": "false_positive", "reviewed_by": "Mme Martin"},
        )
    ).json()
    assert reviewed["status"] == "false_positive"
    assert reviewed["reviewed_by"] == "Mme Martin"
    assert reviewed["reviewed_at"] is not None

    # Filtrage par statut de revue (base des stats de faux positifs, Phase 4).
    pending = (await client.get("/alerts?status=pending")).json()
    assert pending == []

    # Retour à pending : la revue est effacée.
    reset = (
        await client.post(f"/alerts/{alert['id']}/review", json={"status": "pending"})
    ).json()
    assert reset["reviewed_by"] is None
    assert reset["reviewed_at"] is None

    bad = await client.post(f"/alerts/{alert['id']}/review", json={"status": "voleur"})
    assert bad.status_code == 422


async def test_media_urls_conflict_when_missing(client, db_sessionmaker):
    camera = await create_camera(client)
    payload = behavior_alert_payload(camera["id"])
    payload["alert"]["clip_object_key"] = None
    payload["alert"]["thumbnail_object_key"] = None
    async with db_sessionmaker() as session:
        await handle_worker_event(session, payload)

    alert = (await client.get("/alerts")).json()[0]
    assert (await client.get(f"/alerts/{alert['id']}/clip-url")).status_code == 409
    assert (await client.get(f"/alerts/{alert['id']}/thumbnail-url")).status_code == 409


async def test_unknown_alert_is_404(client):
    assert (await client.get("/alerts/nope")).status_code == 404
    assert (
        await client.post("/alerts/nope/review", json={"status": "confirmed"})
    ).status_code == 404
