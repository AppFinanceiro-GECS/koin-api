"""
#45: sessão mobile com refresh token rotativo, logout e revogação.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, decode_token
from app.models.refresh_token import RefreshToken

PASSWORD = "TestPass123!"
NEW_PASSWORD = "OutraSenha456!"


async def _login(client, device_name=None):
    body = {"email": "test@example.com", "password": PASSWORD}
    if device_name:
        body["device_name"] = device_name
    response = await client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _refresh(client, refresh_token):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})


def _auth(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_refresh_rotaciona_e_o_antigo_deixa_de_valer(client, test_user):
    tokens = await _login(client)

    rotated = await _refresh(client, tokens["refresh_token"])
    assert rotated.status_code == 200
    novo = rotated.json()
    assert novo["refresh_token"] != tokens["refresh_token"]
    assert (await client.get("/api/v1/auth/me", headers=_auth(novo))).status_code == 200

    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


async def test_reuso_de_token_trocado_revoga_a_familia(client, test_user):
    """Critério de aceite: reuso de refresh rotacionado → 401 e sessões revogadas."""
    tokens = await _login(client)
    legitimo = (await _refresh(client, tokens["refresh_token"])).json()

    # atacante usa a cópia antiga
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401
    # o aparelho legítimo também perde a sessão e precisa logar de novo
    assert (await _refresh(client, legitimo["refresh_token"])).status_code == 401


async def test_reuso_nao_derruba_outros_aparelhos(client, test_user):
    celular = await _login(client, "celular")
    tablet = await _login(client, "tablet")
    await _refresh(client, celular["refresh_token"])
    await _refresh(client, celular["refresh_token"])  # reuso no celular

    assert (await _refresh(client, tablet["refresh_token"])).status_code == 200


async def test_logout_invalida_o_refresh(client, test_user):
    """Critério de aceite: depois do logout, o refresh antigo → 401."""
    tokens = await _login(client)

    response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 204
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


@pytest.mark.parametrize("token", ["lixo", ""])
async def test_logout_com_token_invalido_e_idempotente(client, test_user, token):
    response = await client.post("/api/v1/auth/logout", json={"refresh_token": token})
    assert response.status_code == 204


async def test_logout_all_derruba_todos_os_aparelhos(client, test_user):
    celular = await _login(client, "celular")
    tablet = await _login(client, "tablet")

    response = await client.post("/api/v1/auth/logout-all", headers=_auth(celular))
    assert response.status_code == 204
    for tokens in (celular, tablet):
        assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


async def test_trocar_senha_mantem_so_o_aparelho_atual(client, test_user):
    atual = await _login(client, "celular")
    outro = await _login(client, "notebook")

    response = await client.post(
        "/api/v1/users/me/change-password",
        headers=_auth(atual),
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert (await _refresh(client, outro["refresh_token"])).status_code == 401
    assert (await _refresh(client, atual["refresh_token"])).status_code == 200


async def test_redefinir_senha_derruba_todas_as_sessoes(client, test_user, db_session):
    tokens = await _login(client)
    from app.modules.auth.services.password_reset import assign_reset_token

    reset_token = assign_reset_token(test_user)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/auth/reset-password/{reset_token}", json={"password": NEW_PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401
    # o login automático da redefinição abre uma sessão nova e válida
    assert (await _refresh(client, response.json()["refresh_token"])).status_code == 200


async def test_admin_desativar_usuario_revoga_sessoes(client, test_user, db_session):
    from app.core.security import get_password_hash
    from app.models.user import User

    admin = User(
        email="admin@example.com",
        hashed_password=get_password_hash(PASSWORD),
        name="Admin",
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.commit()
    tokens = await _login(client)

    response = await client.patch(
        f"/api/v1/admin/users/{test_user.id}",
        headers={"Authorization": f"Bearer {create_access_token(admin.id)}"},
        json={"is_active": False},
    )
    assert response.status_code == 200, response.text
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


async def test_refresh_expirado_e_recusado(client, test_user, db_session):
    tokens = await _login(client)
    jti = decode_token(tokens["refresh_token"])["jti"]
    row = await db_session.get(RefreshToken, jti)
    row.expires_at = row.created_at - timedelta(seconds=1)
    await db_session.commit()

    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


async def test_refresh_sem_jti_de_antes_da_45_e_recusado(client, test_user):
    import jwt

    legado = jwt.encode(
        {"sub": str(test_user.id), "type": "refresh", "exp": 4102444800},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    assert (await _refresh(client, legado)).status_code == 401


async def test_access_token_nao_serve_como_refresh(client, test_user):
    tokens = await _login(client)
    assert (await _refresh(client, tokens["access_token"])).status_code == 401


async def test_aparelhos_conectados_e_encerrar_um(client, test_user):
    celular = await _login(client, "iPhone de Teste")
    notebook = await _login(client, "Notebook")
    celular = (await _refresh(client, celular["refresh_token"])).json()

    response = await client.get("/api/v1/users/me/sessions", headers=_auth(celular))
    assert response.status_code == 200
    sessions = response.json()
    assert {s["device_name"] for s in sessions} == {"iPhone de Teste", "Notebook"}
    assert [s["current"] for s in sessions if s["device_name"] == "iPhone de Teste"] == [True]

    alvo = next(s["id"] for s in sessions if s["device_name"] == "Notebook")
    response = await client.delete(f"/api/v1/users/me/sessions/{alvo}", headers=_auth(celular))
    assert response.status_code == 204
    assert (await _refresh(client, notebook["refresh_token"])).status_code == 401
    remaining = (await client.get("/api/v1/users/me/sessions", headers=_auth(celular))).json()
    assert [s["device_name"] for s in remaining] == ["iPhone de Teste"]


async def test_nao_encerra_sessao_de_outro_usuario(client, test_user, db_session):
    tokens = await _login(client)
    jti = decode_token(tokens["refresh_token"])["jti"]
    family = await db_session.scalar(select(RefreshToken.family_id).where(RefreshToken.jti == jti))
    intruso = create_access_token(test_user.id + 999)

    response = await client.delete(
        f"/api/v1/users/me/sessions/{family}", headers={"Authorization": f"Bearer {intruso}"}
    )
    assert response.status_code in (401, 404)
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 200


def test_tempos_padrao_de_sessao_mobile():
    from app.core.config import Settings

    defaults = Settings(_env_file=None)
    assert defaults.access_token_expire_minutes == 15
    assert 30 <= defaults.refresh_token_expire_days <= 60
