from .conftest import create_camera


async def test_settings_default_empty(client):
    camera = await create_camera(client)
    assert (await client.get(f"/cameras/{camera['id']}/settings")).json() == {}


async def test_put_settings_persists_and_notifies_worker(client, fake_redis):
    camera = await create_camera(client)
    payload = {"alert_threshold": 45.0, "dwell_seconds": 20.0}

    stored = (
        await client.put(f"/cameras/{camera['id']}/settings", json=payload)
    ).json()
    assert stored == payload
    assert (await client.get(f"/cameras/{camera['id']}/settings")).json() == payload

    assert len(fake_redis.published) == 1
    channel, command = fake_redis.published[0]
    assert channel == f"camera_commands:{camera['id']}"
    assert command == {"action": "update_settings", "settings": payload}


async def test_put_settings_rejects_unknown_keys(client, fake_redis):
    camera = await create_camera(client)
    response = await client.put(
        f"/cameras/{camera['id']}/settings", json={"score_magique": 1}
    )
    assert response.status_code == 422
    assert fake_redis.published == []


async def test_put_settings_rejects_invalid_values(client):
    camera = await create_camera(client)
    response = await client.put(
        f"/cameras/{camera['id']}/settings", json={"alert_threshold": -5}
    )
    assert response.status_code == 422


async def test_settings_for_unknown_camera_is_404(client):
    assert (await client.get("/cameras/nope/settings")).status_code == 404
