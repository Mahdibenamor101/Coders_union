from app.events import handle_worker_event
from app.models import Camera, Clip

from .conftest import create_camera


async def _get(db_sessionmaker, model, pk):
    async with db_sessionmaker() as session:
        return await session.get(model, pk)


async def test_clip_ready_event_updates_clip(client, fake_redis, db_sessionmaker):
    camera = await create_camera(client)
    clip = (await client.post(f"/cameras/{camera['id']}/clip", json={})).json()

    async with db_sessionmaker() as session:
        await handle_worker_event(
            session,
            {
                "type": "clip_ready",
                "clip_id": clip["id"],
                "object_key": f"{camera['id']}/{clip['id']}.mp4",
                "duration_seconds": 40.0,
            },
        )

    row = await _get(db_sessionmaker, Clip, clip["id"])
    assert row.status == "ready"
    assert row.object_key == f"{camera['id']}/{clip['id']}.mp4"
    assert row.duration_seconds == 40.0


async def test_clip_failed_event_records_error(client, fake_redis, db_sessionmaker):
    camera = await create_camera(client)
    clip = (await client.post(f"/cameras/{camera['id']}/clip", json={})).json()

    async with db_sessionmaker() as session:
        await handle_worker_event(
            session,
            {"type": "clip_failed", "clip_id": clip["id"], "error": "no frames"},
        )

    row = await _get(db_sessionmaker, Clip, clip["id"])
    assert row.status == "failed"
    assert row.error == "no frames"


async def test_camera_status_event_updates_camera(client, db_sessionmaker):
    camera = await create_camera(client)
    assert camera["status"] == "offline"

    async with db_sessionmaker() as session:
        await handle_worker_event(
            session,
            {"type": "camera_status", "camera_id": camera["id"], "status": "online"},
        )

    row = await _get(db_sessionmaker, Camera, camera["id"])
    assert row.status == "online"
    assert row.last_seen_at is not None


async def test_unknown_targets_are_ignored(db_sessionmaker):
    async with db_sessionmaker() as session:
        await handle_worker_event(
            session, {"type": "clip_ready", "clip_id": "missing"}
        )
        await handle_worker_event(
            session, {"type": "camera_status", "camera_id": "missing"}
        )
        await handle_worker_event(session, {"type": "unknown_event"})
