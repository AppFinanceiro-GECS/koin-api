#!/usr/bin/env python3
"""
Exporta em CSV as contas criadas com o código de um evento (tabela event_signups).

Por padrão sai só quem marcou "Quero receber novidades" e continua com a conta ativa:
é a lista que pode receber contato depois. Contas desativadas (exclusão pedida) nunca saem.

Uso:
    python scripts/export_event_leads.py > leads.csv
    python scripts/export_event_leads.py --source stand-2026-11-28 --todos
    python scripts/export_event_leads.py --resumo

Na VM (dentro do container da hml):
    docker exec koin-hml-api-1 python scripts/export_event_leads.py > leads.csv
"""

import argparse
import asyncio
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import EventSignup, User

COLUMNS = [
    "nome",
    "email",
    "evento",
    "cadastro_em",
    "email_confirmado_em",
    "aceita_novidades",
    "aceite_em",
    "versao_do_aceite",
    "brinde_entregue_em",
]


def _iso(value) -> str:
    return value.isoformat(timespec="seconds") if value else ""


async def main(source: str | None, everyone: bool, summary: bool) -> None:
    query = (
        select(EventSignup, User)
        .join(User, User.id == EventSignup.user_id)
        .where(User.is_active.is_(True))
        .order_by(EventSignup.id)
    )
    if source:
        query = query.where(EventSignup.source == source)
    if not everyone and not summary:
        query = query.where(EventSignup.marketing_opt_in.is_(True))

    async with async_session_maker() as db:
        rows = (await db.execute(query)).all()

    if summary:
        verified = sum(1 for s, _ in rows if s.email_verified_at)
        print(f"cadastros: {len(rows)}")
        print(f"e-mail confirmado: {verified}")
        print(f"aceitam novidades: {sum(1 for s, _ in rows if s.marketing_opt_in)}")
        print(f"brindes entregues: {sum(1 for s, _ in rows if s.gift_delivered_at)}")
        return

    writer = csv.writer(sys.stdout)
    writer.writerow(COLUMNS)
    for signup, user in rows:
        writer.writerow(
            [
                user.name,
                user.email,
                signup.source,
                _iso(signup.created_at),
                _iso(signup.email_verified_at),
                "sim" if signup.marketing_opt_in else "não",
                _iso(signup.marketing_opt_in_at),
                signup.consent_version,
                _iso(signup.gift_delivered_at),
            ]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--source", help="só um evento (EVENT_SIGNUP_SOURCE)")
    parser.add_argument(
        "--todos", action="store_true", help="inclui quem não aceitou receber novidades"
    )
    parser.add_argument("--resumo", action="store_true", help="só os totais, para o dia do stand")
    args = parser.parse_args()
    asyncio.run(main(args.source, args.todos, args.resumo))
