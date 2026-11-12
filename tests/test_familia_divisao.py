"""
Divisão das despesas da casa: quem pagou o quê, a parte de cada um, quem deve a quem e o
acerto. E entrar na família com o código do convite, para quem já tem conta.
Dados fictícios.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.security import create_access_token, get_password_hash
from app.core.utils import utc_now
from app.models import Invitation
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.modules.household.services.family_split import MemberSplit, suggest_transfers

EMAIL_SERVICE = "app.modules.household.routers.family.email_service.send_invitation"
DIA = date(2026, 11, 10)


async def _user(db, email, name):
    user = User(email=email, hashed_password=get_password_hash("Pass123!"), name=name)
    db.add(user)
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _expense(db, user, amount, ownership="household", category=None, when=DIA):
    account = Account(user_id=user.id, name=f"Conta {user.id}", type="checking", balance=0)
    db.add(account)
    await db.flush()
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            category_id=category.id if category else None,
            type="expense",
            amount=Decimal(amount),
            date=when,
            description="Despesa fictícia",
            ownership_type=ownership,
        )
    )
    await db.commit()


@pytest.fixture
def no_email(monkeypatch):
    monkeypatch.setattr(EMAIL_SERVICE, lambda **kwargs: True)


async def _casal(client, db):
    """Ana cria a família; Bruno já tinha conta (e família só dele) e entra com o código"""
    ana, ana_h = await _user(db, "ana@example.com", "Ana Teste")
    bruno, bruno_h = await _user(db, "bruno@example.com", "Bruno Teste")
    assert (await client.post("/api/v1/family", headers=ana_h, json={})).status_code == 201
    assert (await client.post("/api/v1/family", headers=bruno_h, json={})).status_code == 201

    invite = await client.post(
        "/api/v1/family/invite", headers=ana_h, json={"email": "bruno@example.com"}
    )
    assert invite.status_code == 201, invite.text
    joined = await client.post(
        "/api/v1/family/join", headers=bruno_h, json={"code": invite.json()["code"]}
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["member_count"] == 2
    return ana, ana_h, bruno, bruno_h


async def test_quem_ja_tem_conta_entra_com_o_codigo(client, db_session, no_email):
    ana, ana_h, bruno, bruno_h = await _casal(client, db_session)

    ctx = (await client.get("/api/v1/family/context", headers=bruno_h)).json()
    assert ctx["is_owner"] is False
    assert {m["user_email"] for m in ctx["members"]} == {"ana@example.com", "bruno@example.com"}

    # o convite foi usado
    again = await client.post(
        "/api/v1/family/join",
        headers=bruno_h,
        json={"code": (await db_session.get(Invitation, 1)).token},
    )
    assert again.status_code == 400


async def test_codigo_de_outro_email_nao_entra(client, db_session, no_email):
    _, ana_h = await _user(db_session, "ana@example.com", "Ana")
    _, intruso_h = await _user(db_session, "intruso@example.com", "Intruso")
    await client.post("/api/v1/family", headers=ana_h, json={})
    invite = await client.post(
        "/api/v1/family/invite", headers=ana_h, json={"email": "bruno@example.com"}
    )

    response = await client.post(
        "/api/v1/family/join", headers=intruso_h, json={"code": invite.json()["code"]}
    )

    assert response.status_code == 403
    assert "outro e-mail" in response.json()["detail"]


async def test_quem_divide_outra_familia_precisa_sair_antes(client, db_session, no_email):
    _, ana_h, _, _ = await _casal(client, db_session)
    _, carla_h = await _user(db_session, "carla@example.com", "Carla")
    await client.post("/api/v1/family", headers=carla_h, json={})
    # Ana (família com Bruno) é convidada pela Carla
    invite = await client.post(
        "/api/v1/family/invite", headers=carla_h, json={"email": "ana@example.com"}
    )

    response = await client.post(
        "/api/v1/family/join", headers=ana_h, json={"code": invite.json()["code"]}
    )

    assert response.status_code == 409


async def test_convite_expirado(client, db_session, no_email):
    _, ana_h = await _user(db_session, "ana@example.com", "Ana")
    _, bruno_h = await _user(db_session, "bruno@example.com", "Bruno")
    await client.post("/api/v1/family", headers=ana_h, json={})
    invite = await client.post(
        "/api/v1/family/invite", headers=ana_h, json={"email": "bruno@example.com"}
    )
    inv = await db_session.get(Invitation, invite.json()["invitation_id"])
    inv.expires_at = utc_now() - timedelta(days=1)
    await db_session.commit()

    response = await client.post(
        "/api/v1/family/join", headers=bruno_h, json={"code": invite.json()["code"]}
    )

    assert response.status_code == 400
    assert "expirado" in response.json()["detail"]


async def test_divisao_igual_mostra_quem_deve_a_quem(client, db_session, no_email):
    ana, ana_h, bruno, bruno_h = await _casal(client, db_session)
    mercado = Category(user_id=ana.id, name="Mercado", type="expense")
    db_session.add(mercado)
    await db_session.flush()
    await _expense(db_session, ana, "300.00", category=mercado)
    await _expense(db_session, bruno, "100.00")
    await _expense(db_session, bruno, "999.00", ownership="personal")  # pessoal não entra
    await _expense(db_session, ana, "50.00", when=date(2026, 10, 31))  # outro mês

    body = (
        await client.get(
            "/api/v1/family/split", headers=bruno_h, params={"year": 2026, "month": 11}
        )
    ).json()

    assert body["total"] == 400.0
    assert body["split_mode"] == "equal"
    by_name = {m["name"]: m for m in body["members"]}
    assert by_name["Ana"]["paid"] == 300.0 and by_name["Ana"]["balance"] == 100.0
    assert by_name["Bruno"]["paid"] == 100.0 and by_name["Bruno"]["balance"] == -100.0
    assert by_name["Bruno"]["is_me"] is True
    assert body["transfers"] == [
        {
            "from_user_id": bruno.id,
            "from_name": "Bruno",
            "to_user_id": ana.id,
            "to_name": "Ana",
            "amount": 100.0,
        }
    ]
    assert body["categories"][0] == {"name": "Mercado", "amount": 300.0}
    assert body["is_settled"] is False


async def test_divisao_proporcional_e_acerto(client, db_session, no_email):
    ana, ana_h, bruno, bruno_h = await _casal(client, db_session)
    await _expense(db_session, ana, "300.00")
    await _expense(db_session, bruno, "100.00")
    ctx = (await client.get("/api/v1/family/context", headers=ana_h)).json()
    member = {m["user_email"]: m["id"] for m in ctx["members"]}

    # Ana ganha mais: fica com 60% das despesas da casa
    shares = await client.put(
        "/api/v1/family/shares",
        headers=ana_h,
        json={
            "shares": [
                {"member_id": member["ana@example.com"], "share_percent": 60},
                {"member_id": member["bruno@example.com"], "share_percent": 40},
            ]
        },
    )
    assert shares.status_code == 200, shares.text
    split = (
        await client.get("/api/v1/family/split", headers=ana_h, params={"year": 2026, "month": 11})
    ).json()
    assert split["split_mode"] == "custom"
    assert [t["amount"] for t in split["transfers"]] == [60.0]

    # Bruno faz o Pix e registra o acerto
    settled = await client.post(
        "/api/v1/family/settlements",
        headers=bruno_h,
        json={"to_user_id": ana.id, "amount": 60, "year": 2026, "month": 11},
    )
    assert settled.status_code == 201, settled.text
    assert settled.json()["is_settled"] is True
    assert settled.json()["transfers"] == []
    settlement_id = settled.json()["settlements"][0]["id"]

    # desfazer volta o saldo
    assert (
        await client.delete(f"/api/v1/family/settlements/{settlement_id}", headers=bruno_h)
    ).status_code == 204
    split = (
        await client.get("/api/v1/family/split", headers=ana_h, params={"year": 2026, "month": 11})
    ).json()
    assert split["is_settled"] is False


async def test_so_o_dono_define_as_partes_e_elas_somam_100(client, db_session, no_email):
    _, ana_h, _, bruno_h = await _casal(client, db_session)
    ctx = (await client.get("/api/v1/family/context", headers=ana_h)).json()
    ids = [m["id"] for m in ctx["members"]]

    by_member = await client.put(
        "/api/v1/family/shares",
        headers=bruno_h,
        json={"shares": [{"member_id": ids[0], "share_percent": 50}]},
    )
    wrong_sum = await client.put(
        "/api/v1/family/shares",
        headers=ana_h,
        json={"shares": [{"member_id": i, "share_percent": 30} for i in ids]},
    )
    reset = await client.put("/api/v1/family/shares", headers=ana_h, json={"shares": []})

    assert by_member.status_code == 403
    assert wrong_sum.status_code == 422
    assert reset.status_code == 200


def test_transferencias_minimas_entre_tres():
    def m(uid, balance):
        return MemberSplit(
            member_id=uid,
            user_id=uid,
            name=f"M{uid}",
            share_percent=Decimal("33.33"),
            balance=Decimal(balance),
        )

    transfers = suggest_transfers([m(1, "150.00"), m(2, "-100.00"), m(3, "-50.00")])

    assert [(t.from_user_id, t.to_user_id, t.amount) for t in transfers] == [
        (2, 1, Decimal("100.00")),
        (3, 1, Decimal("50.00")),
    ]
