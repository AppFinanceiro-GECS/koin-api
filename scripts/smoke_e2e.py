#!/usr/bin/env python3
"""
Smoke E2E contra um ambiente no ar (#28): o que o deploy precisa provar além do /health.

Fluxo: login → cartão → compra no cartão → listar transações (regressão do #33) →
faturas do cartão → limpeza (compra, cartão e sessão). Não chama a IA: o upload gasta
cota e é coberto pelos testes com a IA simulada.

Uso:
    SMOKE_EMAIL=... SMOKE_PASSWORD=... python scripts/smoke_e2e.py https://hml.exemplo
Sem SMOKE_EMAIL/SMOKE_PASSWORD o script avisa e sai com 0 (ambiente sem usuário de QA).
"""

import os
import sys
from datetime import date

import httpx


class SmokeFailure(Exception):
    pass


def check(response: httpx.Response, expected: int, step: str) -> dict:
    if response.status_code != expected:
        request_id = response.headers.get("X-Request-ID", "-")
        raise SmokeFailure(
            f"{step}: esperado {expected}, veio {response.status_code} "
            f"(request_id={request_id}) {response.text[:300]}"
        )
    print(f"ok  {step}")
    return response.json() if response.content else {}


def run(base_url: str, email: str, password: str, tag: str) -> None:
    api = base_url.rstrip("/") + "/api/v1"
    with httpx.Client(timeout=30, headers={"X-Request-ID": f"smoke-{tag}"}) as http:
        check(http.get(base_url.rstrip("/") + "/health"), 200, "health")
        tokens = check(
            http.post(
                f"{api}/auth/login",
                json={"email": email, "password": password, "device_name": f"smoke {tag}"},
            ),
            200,
            "login",
        )
        http.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        card = tx = None
        try:
            card = check(
                http.post(
                    f"{api}/credit-cards",
                    json={
                        "name": f"Smoke CI {tag}",
                        "credit_limit": 1000,
                        "closing_day": 10,
                        "due_day": 17,
                    },
                ),
                201,
                "criar cartão",
            )
            tx = check(
                http.post(
                    f"{api}/transactions",
                    json={
                        "description": f"Smoke CI {tag}",
                        "amount": "12.34",
                        "date": date.today().isoformat(),
                        "type": "expense",
                        "account_id": card["account_id"],
                        "credit_card_id": card["id"],
                    },
                ),
                201,
                "compra no cartão",
            )
            listing = check(http.get(f"{api}/transactions"), 200, "listar transações")
            if not any(item["id"] == tx["id"] for item in listing.get("items", [])):
                raise SmokeFailure("listar transações: a compra criada não aparece")
            invoices = check(
                http.get(f"{api}/invoices", params={"credit_card_id": card["id"]}),
                200,
                "faturas do cartão",
            )
            if not invoices:
                raise SmokeFailure("faturas do cartão: a compra não gerou fatura")
        finally:
            # limpeza mesmo se um passo falhar: o smoke não deixa lixo na conta de QA
            if tx:
                http.delete(f"{api}/transactions/{tx['id']}")
            if card:
                http.delete(f"{api}/credit-cards/{card['id']}")
            http.post(f"{api}/auth/logout", json={"refresh_token": tokens["refresh_token"]})


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    email, password = os.getenv("SMOKE_EMAIL"), os.getenv("SMOKE_PASSWORD")
    if not email or not password:
        print("::warning::SMOKE_EMAIL/SMOKE_PASSWORD ausentes: smoke E2E pulado")
        return 0
    tag = (os.getenv("GITHUB_SHA") or "local")[:7]
    try:
        run(sys.argv[1], email, password, tag)
    except (SmokeFailure, httpx.HTTPError) as e:
        print(f"::error::smoke E2E falhou: {e}")
        return 1
    print("smoke E2E ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
