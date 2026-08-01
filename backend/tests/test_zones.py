from .conftest import create_camera

SHELF_ZONE = {
    "name": "Rayon parfumerie",
    "type": "rayon",
    "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.6], [0.1, 0.6]],
}


async def test_put_and_get_zones(client, fake_redis):
    camera, auth = await create_camera(client)
    checkout = {
        "name": "Caisse 1",
        "type": "caisse",
        "polygon": [[0.6, 0.6], [0.9, 0.6], [0.9, 0.9]],
    }

    response = await client.put(
        f"/cameras/{camera['id']}/zones",
        json={"zones": [SHELF_ZONE, checkout]},
        headers=auth["headers"],
    )
    assert response.status_code == 200
    zones = response.json()
    assert len(zones) == 2
    assert all(z["id"] for z in zones)

    fetched = (
        await client.get(f"/cameras/{camera['id']}/zones", headers=auth["headers"])
    ).json()
    assert fetched == zones

    # Le worker lit les zones via l'endpoint interne (clé de service).
    internal = (await client.get(f"/internal/cameras/{camera['id']}/zones")).json()
    assert internal == zones


async def test_put_zones_notifies_worker(client, fake_redis):
    camera, auth = await create_camera(client)
    await client.put(
        f"/cameras/{camera['id']}/zones",
        json={"zones": [SHELF_ZONE]},
        headers=auth["headers"],
    )

    assert len(fake_redis.published) == 1
    channel, command = fake_redis.published[0]
    assert channel == f"camera_commands:{camera['id']}"
    assert command["action"] == "update_zones"
    assert command["zones"][0]["name"] == "Rayon parfumerie"


async def test_put_zones_validation(client, fake_redis):
    camera, auth = await create_camera(client)
    url = f"/cameras/{camera['id']}/zones"

    bad_type = {**SHELF_ZONE, "type": "vip"}
    assert (
        await client.put(url, json={"zones": [bad_type]}, headers=auth["headers"])
    ).status_code == 422

    two_points = {**SHELF_ZONE, "polygon": [[0.1, 0.1], [0.5, 0.5]]}
    assert (
        await client.put(url, json={"zones": [two_points]}, headers=auth["headers"])
    ).status_code == 422

    out_of_range = {**SHELF_ZONE, "polygon": [[0.1, 0.1], [1.5, 0.1], [0.5, 0.6]]}
    assert (
        await client.put(url, json={"zones": [out_of_range]}, headers=auth["headers"])
    ).status_code == 422

    assert fake_redis.published == []
    assert (await client.get(url, headers=auth["headers"])).json() == []
