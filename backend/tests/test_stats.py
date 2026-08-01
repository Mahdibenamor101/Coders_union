from app.events import handle_worker_event

from .conftest import create_camera
from .test_alerts import behavior_alert_payload


async def seed_alerts(client, db_sessionmaker):
    camera = await create_camera(client)
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
    return camera


async def test_alerts_per_day_counts_today(client, db_sessionmaker):
    await seed_alerts(client, db_sessionmaker)
    days = (await client.get("/stats/alerts-per-day?days=7")).json()
    assert len(days) == 7
    assert days[-1]["count"] == 4
    assert sum(d["count"] for d in days[:-1]) == 0


async def test_rule_stats_and_false_positive_rate(client, db_sessionmaker):
    await seed_alerts(client, db_sessionmaker)
    alerts = (await client.get("/alerts?rule=dissimulation")).json()

    # 2 revues : 1 faux positif, 1 confirmée → taux de FP = 0.5.
    await client.post(
        f"/alerts/{alerts[0]['id']}/review",
        json={"status": "false_positive", "reviewed_by": "r"},
    )
    await client.post(
        f"/alerts/{alerts[1]['id']}/review",
        json={"status": "confirmed", "reviewed_by": "r"},
    )

    stats = (await client.get("/stats/rules")).json()
    by_rule = {entry["rule"]: entry for entry in stats}

    dissimulation = by_rule["dissimulation"]
    assert dissimulation["total"] == 3
    assert dissimulation["pending"] == 1
    assert dissimulation["false_positive"] == 1
    assert dissimulation["confirmed"] == 1
    assert dissimulation["false_positive_rate"] == 0.5

    zone = by_rule["zone_interdite"]
    assert zone["total"] == 1
    assert zone["false_positive_rate"] is None

    # Triées par volume décroissant.
    assert stats[0]["rule"] == "dissimulation"


async def test_stats_empty_database(client):
    assert (await client.get("/stats/rules")).json() == []
    days = (await client.get("/stats/alerts-per-day?days=3")).json()
    assert [d["count"] for d in days] == [0, 0, 0]
