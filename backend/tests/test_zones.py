from .conftest import create_camera

SHELF_ZONE = {
    "name": "Rayon parfumerie",
    "type": "rayon",
    "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.6], [0.1, 0.6]],
}


async def test_put_and_get_zones(client, fake_redis):
    camera = await create_camera(client)
    checkout = {
        "name": "Caisse 1",
        "type": "caisse",
        "polygon": [[0.6, 0.6], [0.9, 0.6], [0.9, 0.9]],
    }

    response = await client.put(
        f"/cameras/{camera['id']}/zones", json={"zones": [SHELF_ZONE, checkout]}
    )
    assert response.status_code == 200
    zones = response.json()
    assert len(zones) == 2
    assert all(z["id"] for z in zones)
    assert zones[0]["type"] == "rayon"

    fetched = (await client.get(f"/cameras/{camera['id']}/zones")).json()
    assert fetched == zones

    # Les zones apparaissent aussi sur la caméra.
    detail = (await client.get(f"/cameras/{camera['id']}")).json()
    assert detail["zones"] == zones


async def test_put_zones_notifies_worker(client, fake_redis):
    camera = await create_camera(client)
    await client.put(f"/cameras/{camera['id']}/zones", json={"zones": [SHELF_ZONE]})

    assert len(fake_redis.published) == 1
    channel, command = fake_redis.published[0]
    assert channel == f"camera_commands:{camera['id']}"
    assert command["action"] == "update_zones"
    assert command["zones"][0]["name"] == "Rayon parfumerie"
    assert command["zones"][0]["id"]


async def test_put_zones_keeps_provided_ids(client, fake_redis):
    camera = await create_camera(client)
    zones = (
        await client.put(f"/cameras/{camera['id']}/zones", json={"zones": [SHELF_ZONE]})
    ).json()

    # Ré-envoi avec le même id : l'id est stable.
    again = (
        await client.put(f"/cameras/{camera['id']}/zones", json={"zones": zones})
    ).json()
    assert again[0]["id"] == zones[0]["id"]


async def test_put_zones_validation(client, fake_redis):
    camera = await create_camera(client)
    url = f"/cameras/{camera['id']}/zones"

    bad_type = {**SHELF_ZONE, "type": "vip"}
    assert (await client.put(url, json={"zones": [bad_type]})).status_code == 422

    two_points = {**SHELF_ZONE, "polygon": [[0.1, 0.1], [0.5, 0.5]]}
    assert (await client.put(url, json={"zones": [two_points]})).status_code == 422

    out_of_range = {**SHELF_ZONE, "polygon": [[0.1, 0.1], [1.5, 0.1], [0.5, 0.6]]}
    assert (await client.put(url, json={"zones": [out_of_range]})).status_code == 422

    # Rien ne doit avoir été publié ni persisté.
    assert fake_redis.published == []
    assert (await client.get(url)).json() == []


async def test_zones_for_unknown_camera_is_404(client):
    response = await client.put(
        "/cameras/unknown/zones", json={"zones": [SHELF_ZONE]}
    )
    assert response.status_code == 404
