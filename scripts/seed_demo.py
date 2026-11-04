#!/usr/bin/env python3
"""
Usuário de demonstração com dados realistas (#53): contas, 2 cartões, 3 meses de
compras, parcelamentos, assinaturas recorrentes (Netflix, Spotify) e uma fatura paga.

Os dados entram pelas rotas reais da API (em processo, sem rede), então faturas,
parcelas e recorrências seguem as mesmas regras do app. Serve para os grupos testarem
o app e como conta de revisão da Apple/Google.

Uso:
    python scripts/seed_demo.py                       # cria se não existir
    python scripts/seed_demo.py --reset               # apaga o demo e recria
    DEMO_PASSWORD=... python scripts/seed_demo.py --email demo@example.com

Na VM: make seed-hml (roda dentro do container da API de homologação).
Faturas sintéticas para testar o upload: tests/fixtures/documents/*.pdf
"""

import argparse
import asyncio
import os
import secrets
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import select, text

from app.core.database import async_session_maker
from app.core.security import create_access_token, get_password_hash, validate_password_or_raise
from app.core.utils import today_br
from app.models.user import User
from app.modules.auth.services.user_setup import setup_new_user

DEFAULT_EMAIL = "demo@example.com"
API = "/api/v1"


def months_back(today: date, n: int) -> tuple[int, int]:
    """(ano, mês) de n meses atrás"""
    total = today.year * 12 + today.month - 1 - n
    return total // 12, total % 12 + 1


def day_in(year: int, month: int, day: int, today: date) -> date:
    """Dia do mês sem passar de hoje (o mês atual ainda não acabou)"""
    return min(date(year, month, day), today)


async def ensure_user(email: str, password: str, reset: bool) -> tuple[User, bool]:
    async with async_session_maker() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user and not reset:
            return user, False
        if user:
            if db.bind.dialect.name == "sqlite":
                # sem isso o SQLite ignora o ON DELETE CASCADE e deixa os dados órfãos
                await db.execute(text("PRAGMA foreign_keys=ON"))
            await db.delete(user)
            await db.commit()
        user = User(
            email=email,
            name="Ana Demo",
            hashed_password=get_password_hash(password),
            is_verified=True,
        )
        db.add(user)
        await db.flush()
        await setup_new_user(db, user.id)
        await db.commit()
        await db.refresh(user)
        return user, True


class Seeder:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.today = today_br()

    async def call(self, method: str, path: str, **kwargs):
        response = await self.client.request(method, API + path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path} → {response.status_code}: {response.text[:300]}")
        return response.json() if response.content else None

    async def load_reference(self):
        accounts = await self.call("GET", "/accounts")
        self.bank = next(a for a in accounts if a["name"] == "Banco")
        categories = await self.call("GET", "/categories")
        self.cat = {(c["name"], c["type"]): c["id"] for c in categories}

    def category(self, name: str, kind: str = "expense") -> int | None:
        return self.cat.get((name, kind))

    async def card(self, name: str, closing: int, due: int, limit: float, last4: str) -> dict:
        return await self.call(
            "POST",
            "/credit-cards",
            json={
                "name": name,
                "credit_limit": limit,
                "closing_day": closing,
                "due_day": due,
                "last_four_digits": last4,
            },
        )

    async def tx(self, description: str, amount: float, when: date, category: str, **extra):
        kind = extra.pop("type", "expense")
        body = {
            "description": description,
            "amount": amount,
            "date": when.isoformat(),
            "type": kind,
            "account_id": extra.pop("account_id", self.bank["id"]),
            "category_id": self.category(category, kind),
            **extra,
        }
        return await self.call("POST", "/transactions", json=body)

    async def card_tx(
        self, card: dict, description: str, amount: float, when: date, category: str, **extra
    ):
        return await self.tx(
            description,
            amount,
            when,
            category,
            account_id=card["account_id"],
            credit_card_id=card["id"],
            **extra,
        )

    async def run(self):
        await self.load_reference()
        nubank = await self.card("Nubank Roxinho", closing=3, due=10, limit=4500, last4="4821")
        itau = await self.card("Itaú Click", closing=25, due=5, limit=8000, last4="7310")

        # Assinaturas: criadas no mês mais antigo, a recorrência gera as próximas
        oldest_year, oldest_month = months_back(self.today, 2)
        for name, amount, day in [("Netflix", 55.90, 12), ("Spotify", 21.90, 15)]:
            await self.card_tx(
                nubank,
                name,
                amount,
                day_in(oldest_year, oldest_month, day, self.today),
                "Assinaturas",
                merchant_name=name,
                create_recurring=True,
                recurring_frequency="monthly",
                recurring_day_of_month=day,
            )

        for back in (2, 1, 0):
            year, month = months_back(self.today, back)

            def d(day, year=year, month=month):
                return day_in(year, month, day, self.today)

            await self.tx("Salário", 6200.00, d(5), "Salário", type="income")
            await self.tx("Aluguel", 1850.00, d(8), "Moradia")
            await self.tx("Conta de luz", 187.40 + back * 11, d(14), "Contas e Serviços")
            await self.card_tx(nubank, "Pão de Açúcar", 412.35 - back * 23, d(6), "Supermercado")
            await self.card_tx(nubank, "iFood", 68.90, d(9), "Alimentação Fora")
            await self.card_tx(nubank, "Uber", 23.50 + back * 4, d(11), "Transporte")
            await self.card_tx(itau, "Drogasil", 54.80, d(17), "Saúde")
            await self.card_tx(itau, "Posto Ipiranga", 220.00, d(20), "Transporte")
            await self.card_tx(itau, "Outback", 186.00 - back * 15, d(22), "Alimentação Fora")

        # Parcelamentos: a primeira parcela cria as futuras (RN005)
        year, month = months_back(self.today, 2)
        await self.card_tx(
            itau,
            "Notebook Dell",
            420.00,
            day_in(year, month, 18, self.today),
            "Compras Online",
            is_installment=True,
            installment_current=1,
            installment_total=10,
            create_future_installments=True,
        )
        year, month = months_back(self.today, 1)
        await self.card_tx(
            nubank,
            "Tênis Nike",
            133.30,
            day_in(year, month, 2, self.today),
            "Vestuário",
            is_installment=True,
            installment_current=1,
            installment_total=3,
            create_future_installments=True,
        )

        # A fatura mais antiga do Nubank já foi paga pela conta do banco (RN006/RN010)
        invoices = await self.call("GET", "/invoices", params={"credit_card_id": nubank["id"]})
        oldest = min(
            invoices, key=lambda i: (i["reference_year"], i["reference_month"]), default=None
        )
        if oldest and float(oldest["total_amount"]) > 0:
            await self.call(
                "POST",
                f"/invoices/{oldest['id']}/pay",
                json={
                    "amount": float(oldest["total_amount"]),
                    "payment_account_id": self.bank["id"],
                    "payment_date": self.today.isoformat(),
                    "payment_method": "pix",
                },
            )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--email", default=os.getenv("DEMO_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--reset", action="store_true", help="apaga o usuário demo e recria")
    args = parser.parse_args()

    password = os.getenv("DEMO_PASSWORD") or secrets.token_urlsafe(12)
    validate_password_or_raise(password)

    user, created = await ensure_user(args.email, password, args.reset)
    if not created:
        print(f"{args.email} já existe (id {user.id}); use --reset para recriar.")
        return 0

    from app.main import app

    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://seed", headers=headers
    ) as client:
        await Seeder(client).run()

    print(f"Usuário demo pronto: {args.email} (id {user.id})")
    if not os.getenv("DEMO_PASSWORD"):
        print(f"Senha gerada: {password}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
