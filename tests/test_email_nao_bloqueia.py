"""
#22: o SMTP síncrono não roda no event loop e falha de e-mail não vira 500.
"""

import threading

import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.core.services.email_service import EmailService
from app.models.user import User

ADMIN_EMAIL_SERVICE = "app.modules.admin.routers.admin.email_service"


@pytest_asyncio.fixture
async def admin_headers(db_session):
    admin = User(
        email="admin@example.com",
        hashed_password=get_password_hash("TestPass123!"),
        name="Admin",
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(admin.id)}"}


async def test_convite_envia_fora_do_event_loop(client, admin_headers, monkeypatch):
    loop_thread = threading.get_ident()
    threads = []

    def fake_send(**kwargs):
        threads.append(threading.get_ident())
        return True

    monkeypatch.setattr(f"{ADMIN_EMAIL_SERVICE}.send_invitation", fake_send)

    response = await client.post(
        "/api/v1/admin/invitations", headers=admin_headers, json={"email": "nova@example.com"}
    )

    assert response.status_code == 201
    assert threads and threads[0] != loop_thread


async def test_reset_pelo_admin_sem_email_nao_da_500(
    client, admin_headers, test_user, db_session, monkeypatch
):
    await db_session.commit()
    monkeypatch.setattr(f"{ADMIN_EMAIL_SERVICE}.send_password_reset", lambda **kwargs: False)

    response = await client.post(
        f"/api/v1/admin/users/{test_user.id}/reset-password", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["email_sent"] is False


async def test_troca_de_senha_avisa_em_segundo_plano(client, test_user, db_session, monkeypatch):
    await db_session.commit()
    loop_thread = threading.get_ident()
    sent = []
    monkeypatch.setattr(
        "app.modules.auth.routers.users.email_service.send_password_changed_notification",
        lambda email, name: sent.append((email, threading.get_ident())),
    )

    response = await client.post(
        "/api/v1/users/me/change-password",
        headers={"Authorization": f"Bearer {create_access_token(test_user.id)}"},
        json={"current_password": "TestPass123!", "new_password": "OutraSenha456!"},
    )

    assert response.status_code == 200
    assert sent and sent[0][0] == test_user.email
    assert sent[0][1] != loop_thread


def test_message_id_usa_o_dominio_do_remetente(monkeypatch):
    service = EmailService()
    service.user = "conta"
    service.password = "segredo"
    service.from_email = "nao-responda@koin.com.br"
    captured = {}

    class FakeSMTP:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def sendmail(self, sender, to, message):
            captured["message"] = message

    monkeypatch.setattr(service, "_get_connection", lambda: FakeSMTP())

    assert service.send_email("a@example.com", "Assunto", "<p>oi</p>")
    message_id = next(
        line for line in captured["message"].splitlines() if line.startswith("Message-ID:")
    )
    assert message_id.rstrip().endswith("@koin.com.br>")
