from .conftest import create_camera


async def test_settings_default_empty(client):
    camera, auth = await create_camera(client)
    assert (
        await client.get(f"/cameras/{camera['id']}/settings", headers=auth["headers"])
    ).json() == {}


async def test_put_settings_persists_and_notifies_worker(client, fake_redis):
    camera, auth = await create_camera(client)
    payload = {"alert_threshold": 45.0, "dwell_seconds": 20.0}

    stored = (
        await client.put(
            f"/cameras/{camera['id']}/settings", json=payload, headers=auth["headers"]
        )
    ).json()
    assert stored == payload

    # Le worker lit les seuils via l'endpoint interne (enrichis du flag tenant).
    internal = (await client.get(f"/internal/cameras/{camera['id']}/settings")).json()
    assert internal == {**payload, "multimodal_verification": True}

    assert len(fake_redis.published) == 1
    channel, command = fake_redis.published[0]
    assert channel == f"camera_commands:{camera['id']}"
    assert command == {"action": "update_settings", "settings": payload}


async def test_put_settings_rejects_unknown_keys(client, fake_redis):
    camera, auth = await create_camera(client)
    response = await client.put(
        f"/cameras/{camera['id']}/settings",
        json={"score_magique": 1},
        headers=auth["headers"],
    )
    assert response.status_code == 422
    assert fake_redis.published == []
