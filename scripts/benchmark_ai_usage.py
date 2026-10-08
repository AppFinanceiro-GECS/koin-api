"""Opt-in hml run: 30 unique synthetic invoices, metadata-only cost report.

Never runs on import. Authentication comes from environment, never CLI arguments.
"""

import argparse
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import fitz
import httpx


def synthetic_invoice(index, run_id):
    doc = fitz.open()
    page_count = 1 + index % 3
    for page_index in range(page_count):
        page = doc.new_page()
        text = (
            "FATURA DE CARTAO - DADOS TOTALMENTE SINTETICOS\n"
            f"Identificador de teste: {run_id}-{index}-{page_index}\n"
            "Banco Nubank - Cartao final 0000\n"
            "Vencimento 20/10/2026\n"
            "Lancamentos atuais\n"
            f"01/10/2026 LOJA SINTETICA {index}-{page_index} 10,00\n"
            f"02/10/2026 SERVICO SINTETICO {index}-{page_index} 20,00\n"
            f"Total da fatura {30 * page_count},00\n"
        )
        page.insert_text((50, 50), text, fontsize=12)
    try:
        return doc.tobytes()
    finally:
        doc.close()


async def run(args, transport=None):
    url = urlsplit(args.base_url)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("Use uma URL base sem credenciais, query ou fragmento")
    user_token = os.environ.get("KOIN_BENCHMARK_USER_TOKEN")
    admin_token = os.environ.get("KOIN_BENCHMARK_ADMIN_TOKEN")
    if not user_token or not admin_token:
        raise ValueError("Configure os tokens de usuario e administrador no ambiente")
    start = datetime.now(UTC).isoformat()
    run_id = uuid.uuid4().hex
    rows = []
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/") + "/",
        timeout=180,
        follow_redirects=False,
        transport=transport,
    ) as client:
        for index in range(args.count):
            response = await client.post(
                "api/v1/documents/async",
                headers={"Authorization": f"Bearer {user_token}"},
                files={
                    "file": (
                        f"synthetic-{run_id}-{index}.pdf",
                        synthetic_invoice(index, run_id),
                        "application/pdf",
                    )
                },
            )
            if response.status_code != 202:
                raise ValueError(f"Upload bloqueado, HTTP {response.status_code}")
            document_id = response.json()["id"]
            status = "processing"
            for _ in range(args.poll_attempts):
                await asyncio.sleep(args.poll_interval)
                document = await client.get(
                    f"api/v1/documents/{document_id}",
                    headers={"Authorization": f"Bearer {user_token}"},
                )
                if document.status_code != 200:
                    raise ValueError(f"Polling falhou, HTTP {document.status_code}")
                status = document.json()["status"]
                if status in ("completed", "failed"):
                    break
            usage = await client.get(
                "api/v1/admin/ai-usage",
                headers={"Authorization": f"Bearer {admin_token}"},
                params={"from": start, "group_by": "model", "document_id": document_id},
            )
            if usage.status_code != 200:
                raise ValueError(f"Relatorio falhou, HTTP {usage.status_code}")
            groups = usage.json()["items"]
            known = bool(groups) and all(row["unmeasured_calls"] == 0 for row in groups)
            cost = sum((Decimal(str(row["measured_cost_usd"])) for row in groups), Decimal("0"))
            rows.append(
                {
                    "document_id": document_id,
                    "status": status,
                    "usage": groups,
                    "cost_usd": str(cost) if known else None,
                }
            )
    measured = [row for row in rows if row["cost_usd"] is not None]
    total = sum((Decimal(row["cost_usd"]) for row in measured), Decimal("0"))
    accepted = (
        len(rows) >= 30
        and all(row["status"] == "completed" for row in rows)
        and len(measured) == len(rows)
    )
    report = {
        "run_id": run_id,
        "started_at": start,
        "base_url": args.base_url,
        "documents": rows,
        "measured_documents": len(measured),
        "measured_cost_usd": str(total),
        "mean_cost_usd": str(total / len(measured)) if measured else None,
        "acceptance_met": accepted,
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--run-live", action="store_true", help="Autoriza chamadas pagas ao ambiente indicado"
    )
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--output", default="ai-usage-hml.json")
    parser.add_argument("--poll-attempts", type=int, default=90)
    parser.add_argument("--poll-interval", type=float, default=2)
    args = parser.parse_args()
    if not args.run_live:
        parser.error("A execucao exige --run-live")
    if args.count < 30:
        parser.error("Use pelo menos 30 documentos para o criterio de aceite")
    try:
        accepted = asyncio.run(run(args))
    except Exception as error:
        # No exception bodies: HTTP exceptions may contain credential-bearing URLs.
        parser.exit(1, f"Benchmark interrompido: {type(error).__name__}\n")
    parser.exit(0 if accepted else 1, "Relatorio gravado; consulte acceptance_met.\n")


if __name__ == "__main__":
    main()
