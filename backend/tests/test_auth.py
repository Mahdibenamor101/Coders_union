from .conftest import invite_and_accept, register


async def test_register_creates_tenant_and_admin(client):
    auth = await register(client, company="Boutique Neuve")
    me = (await client.get("/auth/me", headers=auth["headers"])).json()
    assert me["role"] == "admin"
    assert me["tenant"]["name"] == "Boutique Neuve"
    assert me["tenant"]["plan"] == "starter"


async def test_register_duplicate_email_conflicts(client):
    auth = await register(client)
    response = await client.post(
        "/auth/register",
        json={
            "company_name": "Autre",
            "email": auth["email"],
            "password": "motdepasse1",
        },
    )
    assert response.status_code == 409


async def test_login_and_bad_credentials(client):
    auth = await register(client)
    ok = await client.post(
        "/auth/login", json={"email": auth["email"], "password": auth["password"]}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = await client.post(
        "/auth/login", json={"email": auth["email"], "password": "mauvais-mdp"}
    )
    assert bad.status_code == 401
    unknown = await client.post(
        "/auth/login", json={"email": "personne@test.fr", "password": "motdepasse1"}
    )
    assert unknown.status_code == 401


async def test_invitation_flow(client):
    admin = await register(client)
    member = await invite_and_accept(client, admin, role="manager", name="Membre Un")

    me = (await client.get("/auth/me", headers=member["headers"])).json()
    assert me["role"] == "manager"

    # Le membre est dans le même tenant que l'admin.
    admin_tenant = (await client.get("/tenant", headers=admin["headers"])).json()
    member_tenant = (await client.get("/tenant", headers=member["headers"])).json()
    assert admin_tenant["id"] == member_tenant["id"]

    users = (await client.get("/users", headers=admin["headers"])).json()
    assert {u["email"] for u in users} == {admin["email"], member["email"]}


async def test_invitation_cannot_be_reused(client):
    admin = await register(client)
    invitation = (
        await client.post(
            "/invitations",
            json={"email": "unique@test.fr", "role": "viewer"},
            headers=admin["headers"],
        )
    ).json()
    token = invitation["invite_url"].split("token=")[1]

    first = await client.post(
        "/auth/invitations/accept", json={"token": token, "password": "motdepasse1"}
    )
    assert first.status_code == 201
    second = await client.post(
        "/auth/invitations/accept", json={"token": token, "password": "motdepasse1"}
    )
    assert second.status_code == 404


async def test_roles_enforced(client):
    admin = await register(client)
    viewer = await invite_and_accept(client, admin, role="viewer")
    manager = await invite_and_accept(client, admin, role="manager")

    # Viewer : lecture seule.
    assert (
        await client.post(
            "/stores", json={"name": "Interdit"}, headers=viewer["headers"]
        )
    ).status_code == 403
    assert (await client.get("/stores", headers=viewer["headers"])).status_code == 200

    # Manager : opérationnel oui, administration non.
    assert (
        await client.post("/stores", json={"name": "OK"}, headers=manager["headers"])
    ).status_code == 201
    assert (
        await client.post(
            "/invitations",
            json={"email": "x@test.fr", "role": "viewer"},
            headers=manager["headers"],
        )
    ).status_code == 403
    assert (await client.get("/users", headers=manager["headers"])).status_code == 403

    # Admin : peut inviter et lister.
    assert (await client.get("/users", headers=admin["headers"])).status_code == 200


async def test_admin_can_delete_user_but_not_self(client):
    admin = await register(client)
    viewer = await invite_and_accept(client, admin, role="viewer")

    me = (await client.get("/auth/me", headers=admin["headers"])).json()
    assert (
        await client.delete(f"/users/{me['id']}", headers=admin["headers"])
    ).status_code == 409

    viewer_me = (await client.get("/auth/me", headers=viewer["headers"])).json()
    assert (
        await client.delete(f"/users/{viewer_me['id']}", headers=admin["headers"])
    ).status_code == 204
    # Le token du viewer supprimé ne fonctionne plus.
    assert (
        await client.get("/auth/me", headers=viewer["headers"])
    ).status_code == 401
