"""
#43: aparelho registrado, push pelo Expo (simulado) e lembretes que viram push.
Nenhum teste chama o Expo de verdade.
"""

import json
from datetime import date, time, timedelta

import httpx
import pytest
from freezegun import freeze_time
from sqlalchemy import select

from app.core.security import create_access_token
from app.core.utils import utc_now
from app.models.document import Document, DocumentStatus
from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationSettings,
    NotificationType,
)
from app.models.push_device import PushDevice
from app.modules.documents.services.document_service import notify_document_result
from app.modules.notifications.services.notification_service import NotificationService
from app.modules.notifications.services.push_delivery import deliver_pending_push

TOKEN = "ExponentPushToken[abcdefghij123456]"
OTHER = "ExponentPushToken[zyxwvutsrq654321]"


def expo(responder):
    """Cliente httpx falso do Expo; responder(messages) devolve a lista de tickets."""
    sent = []

    def handle(request: httpx.Request) -> httpx.Response:
        messages = json.loads(request.content)
        sent.extend(messages)
        return httpx.Response(200, json={"data": responder(messages)})

    return httpx.AsyncClient(transport=httpx.MockTransport(handle)), sent


def all_ok(messages):
    return [{"status": "ok", "id": str(i)} for i, _ in enumerate(messages)]


@pytest.fixture
def auth(test_user):
    return {"Authorization": f"Bearer {create_access_token(test_user.id)}"}


async def _device(db_session, user, token=TOKEN):
    device = PushDevice(user_id=user.id, expo_push_token=token, platform="android")
    db_session.add(device)
    await db_session.commit()
    return device


async def _notify(db_session, user, kind=NotificationType.INVOICE_DUE_3_DAYS):
    notification = await NotificationService(db_session).send_notification(
        user_id=user.id,
        notification_type=kind,
        title="Fatura vence em 3 dias",
        message="A fatura de R$ 90,00 vence em 17/05.",
        action_url="/invoices/1",
    )
    await db_session.commit()
    return notification


# ---------- registro do aparelho ----------


async def test_registrar_listar_e_remover_aparelho(client, auth, test_user, db_session):
    await db_session.commit()
    body = {"expo_push_token": TOKEN, "platform": "ios", "app_version": "1.2.0"}

    first = await client.post("/api/v1/users/me/devices", json=body, headers=auth)
    again = await client.post(
        "/api/v1/users/me/devices", json={**body, "app_version": "1.3.0"}, headers=auth
    )

    assert first.status_code == 200 and again.status_code == 200
    devices = (await client.get("/api/v1/users/me/devices", headers=auth)).json()
    assert len(devices) == 1 and devices[0]["app_version"] == "1.3.0"

    removed = await client.delete(f"/api/v1/users/me/devices/{TOKEN}", headers=auth)
    assert removed.status_code == 204
    assert (await client.get("/api/v1/users/me/devices", headers=auth)).json() == []
    # idempotente
    assert (
        await client.delete(f"/api/v1/users/me/devices/{TOKEN}", headers=auth)
    ).status_code == 204


@pytest.mark.parametrize("token", ["abc", "ExponentPushToken[]", "fcm:xyz"])
async def test_token_invalido_e_recusado(client, auth, db_session, token):
    await db_session.commit()
    response = await client.post(
        "/api/v1/users/me/devices",
        json={"expo_push_token": token, "platform": "android"},
        headers=auth,
    )
    assert response.status_code == 422


async def test_aparelho_passa_para_a_conta_que_logou(client, test_user, db_session):
    from app.core.security import get_password_hash
    from app.models.user import User

    other = User(
        email="outra@example.com", name="Outra", hashed_password=get_password_hash("x" * 8)
    )
    db_session.add(other)
    await _device(db_session, test_user)

    response = await client.post(
        "/api/v1/users/me/devices",
        json={"expo_push_token": TOKEN, "platform": "android"},
        headers={"Authorization": f"Bearer {create_access_token(other.id)}"},
    )

    assert response.status_code == 200
    owners = (await db_session.execute(select(PushDevice.user_id))).scalars().all()
    assert owners == [other.id]


# ---------- entrega ----------


async def test_notificacao_vira_push_uma_vez(db_session, test_user):
    await _device(db_session, test_user)
    await _device(db_session, test_user, OTHER)
    notification = await _notify(db_session, test_user)
    client, sent = expo(all_ok)

    assert await deliver_pending_push(db_session, client) == 1
    assert {m["to"] for m in sent} == {TOKEN, OTHER}
    assert sent[0]["title"] == "Fatura vence em 3 dias"
    assert sent[0]["data"]["action_url"] == "/invoices/1"
    await db_session.refresh(notification)
    assert notification.sent_push is True

    assert await deliver_pending_push(db_session, client) == 0
    assert len(sent) == 2


async def test_app_desinstalado_apaga_o_token(db_session, test_user):
    await _device(db_session, test_user)
    notification = await _notify(db_session, test_user)
    client, _ = expo(
        lambda messages: [
            {"status": "error", "details": {"error": "DeviceNotRegistered"}} for _ in messages
        ]
    )

    assert await deliver_pending_push(db_session, client) == 0

    assert (await db_session.execute(select(PushDevice))).scalars().all() == []
    await db_session.refresh(notification)
    assert notification.sent_push is False


async def test_falha_de_rede_tenta_de_novo(db_session, test_user):
    await _device(db_session, test_user)
    notification = await _notify(db_session, test_user)

    def broken(request):
        raise httpx.ConnectError("sem rede")

    failing = httpx.AsyncClient(transport=httpx.MockTransport(broken))
    assert await deliver_pending_push(db_session, failing) == 0
    await db_session.refresh(notification)
    assert notification.sent_push is False

    client, sent = expo(all_ok)
    assert await deliver_pending_push(db_session, client) == 1
    assert len(sent) == 1


async def test_push_desligado_nas_configuracoes(db_session, test_user):
    await _device(db_session, test_user)
    db_session.add(NotificationSettings(user_id=test_user.id, push_enabled=False))
    await _notify(db_session, test_user)
    client, sent = expo(all_ok)

    assert await deliver_pending_push(db_session, client) == 0
    assert sent == []


async def test_tipo_desligado_nas_preferencias(db_session, test_user):
    await _device(db_session, test_user)
    db_session.add(
        NotificationPreference(
            user_id=test_user.id,
            notification_type=NotificationType.INVOICE_DUE_3_DAYS.value,
            push_enabled=False,
        )
    )
    await _notify(db_session, test_user)
    client, sent = expo(all_ok)

    assert await deliver_pending_push(db_session, client) == 0
    assert sent == []


async def test_horario_silencioso_segura_ate_de_manha(db_session, test_user):
    await _device(db_session, test_user)
    db_session.add(
        NotificationSettings(
            user_id=test_user.id,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(7, 0),
        )
    )
    client, sent = expo(all_ok)

    with freeze_time("2026-05-10 02:00"):  # 23h em Brasília
        await _notify(db_session, test_user)
        assert await deliver_pending_push(db_session, client) == 0
    with freeze_time("2026-05-10 11:00"):  # 8h em Brasília
        assert await deliver_pending_push(db_session, client) == 1
    assert len(sent) == 1


async def test_notificacao_antiga_nao_dispara(db_session, test_user):
    await _device(db_session, test_user)
    notification = await _notify(db_session, test_user)
    notification.created_at = utc_now() - timedelta(days=2)
    await db_session.commit()
    client, sent = expo(all_ok)

    assert await deliver_pending_push(db_session, client) == 0
    assert sent == []


# ---------- lembretes e leitura de fatura ----------


async def test_lembrete_no_dia_do_vencimento(db_session, test_user):
    from decimal import Decimal

    from app.models.account import Account, AccountType
    from app.models.credit_card import CreditCard
    from app.models.credit_card_invoice import CreditCardInvoice
    from app.modules.notifications.services.alert_engine import AlertEngine

    account = Account(user_id=test_user.id, name="Nubank", type=AccountType.CREDIT_CARD.value)
    db_session.add(account)
    await db_session.flush()
    card = CreditCard(
        account_id=account.id,
        user_id=test_user.id,
        credit_limit=Decimal("1000"),
        closing_day=3,
        due_day=10,
    )
    db_session.add(card)
    await db_session.flush()
    db_session.add(
        CreditCardInvoice(
            user_id=test_user.id,
            credit_card_id=card.id,
            reference_month=5,
            reference_year=2026,
            closing_date=date(2026, 5, 3),
            due_date=date(2026, 5, 10),
            total_amount=Decimal("90"),
            status="closed",
        )
    )
    await db_session.commit()

    with freeze_time("2026-05-10 12:00"):
        assert await AlertEngine(db_session).check_invoice_due_dates(test_user) == 1
    await db_session.commit()

    notification = await db_session.scalar(select(Notification))
    assert notification.type == "invoice_due_today"
    assert notification.title == "Fatura vence hoje"


@pytest.mark.parametrize(
    "status,kind",
    [(DocumentStatus.COMPLETED, "document_processed"), (DocumentStatus.FAILED, "document_failed")],
)
async def test_fim_da_leitura_gera_aviso(db_session, test_user, status, kind):
    document = Document(
        user_id=test_user.id,
        file_path="/tmp/x.pdf",
        file_hash="a" * 64,
        file_size=1,
        mime_type="application/pdf",
        original_filename="fatura.pdf",
        status=status,
        error_message="Não conseguimos ler este arquivo."
        if status == DocumentStatus.FAILED
        else None,
        extracted_data={"items": [{"description": "a"}, {"description": "b"}]},
    )
    db_session.add(document)
    await db_session.flush()

    await notify_document_result(db_session, document)
    await db_session.commit()

    notification = await db_session.scalar(select(Notification))
    assert notification.type == kind
    assert notification.action_url == f"/documents/{document.id}"
    if status == DocumentStatus.COMPLETED:
        assert notification.message == "2 compras prontas para conferir."


async def test_fila_da_ia_nao_avisa(db_session, test_user):
    document = Document(
        user_id=test_user.id,
        file_path="/tmp/x.pdf",
        file_hash="b" * 64,
        file_size=1,
        mime_type="application/pdf",
        original_filename="fatura.pdf",
        status=DocumentStatus.WAITING_AI,
    )
    db_session.add(document)
    await db_session.flush()

    await notify_document_result(db_session, document)

    assert await db_session.scalar(select(Notification)) is None


def test_jobs_agendados():
    from apscheduler.triggers.cron import CronTrigger

    from app.core.scheduler import JOBS

    jobs = {job_id: (module, trigger) for module, _, trigger, job_id in JOBS}
    assert jobs["send_pending_push_notifications"][0] == "notifications"
    due = jobs["check_invoice_due_dates"][1]
    assert isinstance(due, CronTrigger)
    assert str(due.fields[due.FIELD_NAMES.index("hour")]) == "9"
