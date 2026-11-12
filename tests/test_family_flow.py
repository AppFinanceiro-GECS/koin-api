"""
Testes para o fluxo de criacao de familia do zero e envio de convite com link copiavel.
"""

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.user import User

EMAIL_SERVICE = "app.modules.household.routers.family.email_service.send_invitation"


@pytest.mark.asyncio
async def test_get_family_context_sem_familia_retorna_403(client, db_session):
    user = User(
        email="solo@example.com",
        hashed_password=get_password_hash("Pass123!"),
        name="Solo User",
    )
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    response = await client.get("/api/v1/family/context", headers=headers)
    assert response.status_code == 403
    assert "família" in response.json()["detail"].lower() or "licença" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_criar_familia_e_convidar_membro(client, db_session, monkeypatch):
    monkeypatch.setattr(EMAIL_SERVICE, lambda **kwargs: True)

    user = User(
        email="chefe@example.com",
        hashed_password=get_password_hash("Pass123!"),
        name="Chefe da Casa",
    )
    db_session.add(user)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    # 1. Iniciar família
    create_res = await client.post("/api/v1/family", headers=headers, json={"nickname": "Pai"})
    assert create_res.status_code == 201, create_res.text
    data = create_res.json()
    assert data["is_owner"] is True
    assert data["can_invite"] is True
    assert data["member_count"] == 1
    assert data["max_members"] >= 5
    assert len(data["members"]) == 1
    assert data["members"][0]["user_email"] == "chefe@example.com"
    assert data["members"][0]["nickname"] == "Pai"
    assert data["members"][0]["role"] == "owner"

    # 2. Tentar criar novamente deve dar 400
    dup_res = await client.post("/api/v1/family", headers=headers, json={})
    assert dup_res.status_code == 400
    assert "já pertence" in dup_res.json()["detail"]

    # 3. GET /family/context agora retorna o contexto
    ctx_res = await client.get("/api/v1/family/context", headers=headers)
    assert ctx_res.status_code == 200
    assert ctx_res.json()["is_owner"] is True

    # 4. Convidar membro devolve link e token
    invite_res = await client.post(
        "/api/v1/family/invite",
        headers=headers,
        json={"email": "esposa@example.com", "nickname": "Esposa"},
    )
    assert invite_res.status_code == 201, invite_res.text
    invite_data = invite_res.json()
    assert invite_data["email"] == "esposa@example.com"
    assert invite_data["token"]
    assert invite_data["invite_url"].endswith(f"/invite/{invite_data['token']}")
