from app.events import handle_worker_event

from .conftest import create_camera
from .test_alerts import behavior_alert_payload


async def seed_alerts(client, db_sessionmaker):
    camera, auth = await create_camera(client)
    async with db_sessionmaker() as session:
        for rule, score in (
            ("dissimulation", 80.0),
            ("dissimulation", 75.0),
            ("dissimulation", 90.0),
            ("zone_interdite", 70.0),
        ):
            await handle_worker_event(
                session, behavior_alert_payload(camera["id"], rule=rule, score=score)
            )
    return camera, auth


async def test_alerts_per_day_counts_today(client, db_sessionmaker):
    _camera, auth = await seed_alerts(client, db_sessionmaker)
    days = (
        await client.get("/stats/alerts-per-day?days=7", headers=auth["headers"])
    ).json()
    assert len(days) == 7
    assert days[-1]["count"] == 4


async def test_rule_stats_and_false_positive_rate(client, db_sessionmaker):
    _camera, auth = await seed_alerts(client, db_sessionmaker)
    alerts = (
        await client.get("/alerts?rule=dissimulation", headers=auth["headers"])
    ).json()

    await client.post(
        f"/alerts/{alerts[0]['id']}/review",
        json={"status": "false_positive"},
        headers=auth["headers"],
    )
    await client.post(
        f"/alerts/{alerts[1]['id']}/review",
        json={"status": "confirmed"},
        headers=auth["headers"],
    )

    stats = (await client.get("/stats/rules", headers=auth["headers"])).json()
    by_rule = {entry["rule"]: entry for entry in stats}
    assert by_rule["dissimulation"]["false_positive_rate"] == 0.5
    assert by_rule["zone_interdite"]["false_positive_rate"] is None
