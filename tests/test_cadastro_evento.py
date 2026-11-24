"""Cadastro pelo código de evento: conta marcada, e-mail confirmado por código e brinde."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.utils import utc_now
from app.models import EventSignup, HouseholdMember, License, User
from app.modules.auth.routers import event_signup as event_module

URL = "/api/v1/auth/event-signup"


@pytest.fixture
def evento(monkeypatch):
    """Liga o evento e guarda os códigos que seriam enviados por e-mail."""
    sent: list[str] = []
    monkeypatch.setattr(settings, "event_signup_code", "KOIN-STAND")
    monkeypatch.setattr(settings, "event_signup_source", "stand-2026-11-28")
    monkeypatch.setattr(settings, "event_signup_ends_at", None)
    monkeypatch.setattr(settings, "event_signup_dev_code", None)
    monkeypatch.setattr(
        event_module.email_service,
        "send_event_verification_code",
        lambda to, name, code: sent.append(code) or True,
    )
    return sent


def _payload(**overrides):
    data = {
        "code": "koin-stand",
        "name": "Ana Visitante",
        "email": "Ana@Example.com",
        "password": "uma senha boa 123",
        "accept_terms": True,
        "marketing_opt_in": True,
    }
    data.update(overrides)
    return data


async def _signup(client, **overrides):
    response = await client.post(URL, json=_payload(**overrides))
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_sem_codigo_configurado_a_rota_nao_existe(client, monkeypatch):
    monkeypatch.setattr(settings, "event_signup_code", None)
    response = await client.post(URL, json=_payload())
    assert response.status_code == 404


async def test_evento_encerrado(client, evento, monkeypatch):
    monkeypatch.setattr(settings, "event_signup_ends_at", utc_now() - timedelta(minutes=1))
    response = await client.post(URL, json=_payload())
    assert response.status_code == 404


async def test_codigo_do_time_vale_com_evento_encerrado(client, evento, monkeypatch, db_session):
    monkeypatch.setattr(settings, "event_signup_ends_at", utc_now() - timedelta(minutes=1))
    monkeypatch.setattr(settings, "event_signup_dev_code", "KOIN-DEV")

    assert (await client.post(URL, json=_payload())).status_code == 400
    await _signup(client, code="koin-dev")

    signup = await db_session.scalar(select(EventSignup))
    assert signup.source == "dev"


async def test_codigo_do_time_sem_evento_configurado(client, evento, monkeypatch):
    monkeypatch.setattr(settings, "event_signup_code", None)
    monkeypatch.setattr(settings, "event_signup_dev_code", "KOIN-DEV")
    assert (await client.post(URL, json=_payload())).status_code == 400
    await _signup(client, code="KOIN-DEV")


async def test_codigo_errado(client, evento):
    response = await client.post(URL, json=_payload(code="00000"))
    assert response.status_code == 400


async def test_termos_sao_obrigatorios(client, evento):
    response = await client.post(URL, json=_payload(accept_terms=False))
    assert response.status_code == 422


async def test_cria_conta_marcada_com_licenca_e_aceite(client, evento, db_session):
    headers = await _signup(client)

    user = await db_session.scalar(select(User).where(User.email == "ana@example.com"))
    assert user and user.license_id and not user.is_verified
    signup = await db_session.scalar(select(EventSignup).where(EventSignup.user_id == user.id))
    assert signup.source == "stand-2026-11-28"
    assert signup.marketing_opt_in and signup.marketing_opt_in_at
    assert signup.consent_version == event_module.CONSENT_VERSION
    license = await db_session.get(License, user.license_id)
    assert license.owner_user_id == user.id
    member = await db_session.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == user.id)
    )
    assert member.role == "owner"
    assert len(evento) == 1

    # a conta já usa o app: contas padrão e licença
    accounts = await client.get("/api/v1/accounts", headers=headers)
    assert accounts.status_code == 200 and len(accounts.json()) >= 1

    status = (await client.get(f"{URL}/me", headers=headers)).json()
    assert status["ticket_number"] == signup.id
    assert status["email_verified"] is False
    assert status["gift_delivered"] is False


async def test_sem_aceite_de_novidades(client, evento, db_session):
    await _signup(client, marketing_opt_in=False)
    signup = await db_session.scalar(select(EventSignup))
    assert not signup.marketing_opt_in and signup.marketing_opt_in_at is None


async def test_email_repetido(client, evento):
    await _signup(client)
    response = await client.post(URL, json=_payload(email="ana@example.com"))
    assert response.status_code == 400


async def test_confirma_email_e_entrega_brinde_uma_vez(client, evento):
    headers = await _signup(client)

    gift = await client.post(f"{URL}/gift", headers=headers)
    assert gift.status_code == 400  # e-mail ainda não confirmado

    wrong = "000000" if evento[0] != "000000" else "111111"
    assert (
        await client.post(f"{URL}/verify", headers=headers, json={"code": wrong})
    ).status_code == 400

    ok = await client.post(f"{URL}/verify", headers=headers, json={"code": evento[0]})
    assert ok.status_code == 200 and ok.json()["email_verified"] is True

    gift = await client.post(f"{URL}/gift", headers=headers)
    assert gift.status_code == 200 and gift.json()["gift_delivered"] is True
    assert (await client.post(f"{URL}/gift", headers=headers)).status_code == 409


async def test_codigo_bloqueia_depois_de_5_erros(client, evento):
    headers = await _signup(client)
    wrong = "000000" if evento[0] != "000000" else "111111"
    for _ in range(event_module.MAX_ATTEMPTS):
        await client.post(f"{URL}/verify", headers=headers, json={"code": wrong})

    blocked = await client.post(f"{URL}/verify", headers=headers, json={"code": evento[0]})
    assert blocked.status_code == 400
    assert "tentativas" in blocked.text


async def test_reenvio_espera_um_minuto(client, evento, db_session):
    headers = await _signup(client)
    assert (await client.post(f"{URL}/resend", headers=headers)).status_code == 429

    signup = await db_session.scalar(select(EventSignup))
    signup.verification_sent_at = utc_now() - timedelta(minutes=2)
    await db_session.commit()

    assert (await client.post(f"{URL}/resend", headers=headers)).status_code == 202
    assert len(evento) == 2
    # o código antigo deixa de valer
    old = await client.post(f"{URL}/verify", headers=headers, json={"code": evento[0]})
    if evento[0] != evento[1]:
        assert old.status_code == 400
    new = await client.post(f"{URL}/verify", headers=headers, json={"code": evento[1]})
    assert new.status_code == 200


async def test_conta_fora_do_evento(client, test_user):
    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
    assert (await client.get(f"{URL}/me", headers=headers)).status_code == 404


async def test_export_sai_so_quem_aceitou_e_esta_ativo(
    client, evento, db_session, monkeypatch, capsys
):
    import importlib.util
    from pathlib import Path

    await _signup(client)  # aceitou
    await _signup(client, email="bia@example.com", marketing_opt_in=False)
    await _signup(client, email="caio@example.com")
    monkeypatch.setattr(settings, "event_signup_dev_code", "KOIN-DEV")
    await _signup(client, email="dev@example.com", code="KOIN-DEV")  # time: fora do export
    caio = await db_session.scalar(select(User).where(User.email == "caio@example.com"))
    caio.is_active = False
    await db_session.commit()

    path = Path(__file__).resolve().parent.parent / "scripts" / "export_event_leads.py"
    spec = importlib.util.spec_from_file_location("export_event_leads", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class _Session:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(module, "async_session_maker", lambda: _Session())

    await module.main(None, everyone=False, summary=False)
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("nome,email")
    assert len(lines) == 2 and "ana@example.com" in lines[1]

    await module.main(None, everyone=False, summary=True)
    assert "cadastros: 2" in capsys.readouterr().out
