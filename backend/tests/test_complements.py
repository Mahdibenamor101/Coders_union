"""Compléments post-Phase 5 : SMTP, vérification multimodale par tenant,
liste interne des caméras pour le superviseur."""

from .conftest import create_camera, register


async def test_invitation_email_sent_when_smtp_configured(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.routers.auth.send_invitation_email",
        lambda to, url, org: sent.append((to, url, org)) or True,
    )
    admin = await register(client, company="Boutique Mail")

    invitation = (
        await client.post(
            "/invitations",
            json={"email": "nouveau@test.fr", "role": "viewer"},
            headers=admin["headers"],
        )
    ).json()

    assert invitation["email_sent"] is True
    assert len(sent) == 1
    to, url, org = sent[0]
    assert to == "nouveau@test.fr"
    assert invitation["invite_url"] == url
    assert org == "Boutique Mail"


async def test_invitation_without_smtp_still_returns_link(client):
    admin = await register(client)
    invitation = (
        await client.post(
            "/invitations",
            json={"email": "x@test.fr", "role": "viewer"},
            headers=admin["headers"],
        )
    ).json()
    assert invitation["email_sent"] is False
    assert "token=" in invitation["invite_url"]


async def test_internal_camera_list_for_supervisor(client):
    camera_a, _ = await create_camera(client, name="Cam A")
    camera_b, _ = await create_camera(client, name="Cam B")

    listed = (await client.get("/internal/cameras")).json()
    assert {entry["id"] for entry in listed} == {camera_a["id"], camera_b["id"]}

    # Clé de service requise.
    denied = await client.get("/internal/cameras", headers={"X-API-Key": "wrong"})
    assert denied.status_code == 401


async def test_multimodal_verification_flag_flows_to_worker(client, fake_redis):
    camera, auth = await create_camera(client)

    # Activée par défaut, exposée au worker via les settings internes.
    tenant = (await client.get("/tenant", headers=auth["headers"])).json()
    assert tenant["multimodal_verification"] is True
    settings = (await client.get(f"/internal/cameras/{camera['id']}/settings")).json()
    assert settings["multimodal_verification"] is True

    # Désactivation par tenant (SPEC §6) : persistée + poussée aux workers.
    updated = (
        await client.patch(
            "/tenant",
            json={"multimodal_verification": False},
            headers=auth["headers"],
        )
    ).json()
    assert updated["multimodal_verification"] is False

    settings = (await client.get(f"/internal/cameras/{camera['id']}/settings")).json()
    assert settings["multimodal_verification"] is False

    channel, command = fake_redis.published[-1]
    assert channel == f"camera_commands:{camera['id']}"
    assert command == {
        "action": "update_settings",
        "settings": {"multimodal_verification": False},
    }
