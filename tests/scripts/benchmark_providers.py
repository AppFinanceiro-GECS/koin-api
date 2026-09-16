"""Benchmark: Gemini vs Mistral extraction on all PDFs."""

import asyncio
import os
import sys
import time

# Setup
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ".")

from dotenv import load_dotenv

load_dotenv()


async def test_provider(provider_name: str, filepath: str) -> dict:
    """Test a single provider on a single PDF. Returns stats."""
    from app.modules.documents.services.llm_ocr_service import LLMOCRService

    # Force provider (bypass smart routing for fair comparison)
    service = LLMOCRService(provider=provider_name)

    with open(filepath, "rb") as f:
        content = f.read()

    filename = os.path.basename(filepath)

    # Force native PDF mode for google
    if provider_name == "google":
        os.environ["GOOGLE_PDF_MODE"] = "native"

    start = time.perf_counter()
    try:
        result = await service.extract_from_image(
            image_content=content,
            mime_type="application/pdf",
            filename=filename,
        )
        elapsed = time.perf_counter() - start

        items = result.get("items", [])
        card_info = result.get("card_info") or {}
        error = result.get("error")
        total_amount = card_info.get("total_amount", 0) or 0
        items_sum = sum(item.get("amount", 0) for item in items)
        diff = abs(items_sum - total_amount) if total_amount else None

        return {
            "provider": provider_name,
            "file": filename,
            "time": elapsed,
            "items": len(items),
            "total_fatura": total_amount,
            "items_sum": items_sum,
            "diff": diff,
            "error": error,
            "card_issuer": card_info.get("card_issuer"),
        }
    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "provider": provider_name,
            "file": filename,
            "time": elapsed,
            "items": 0,
            "total_fatura": 0,
            "items_sum": 0,
            "diff": None,
            "error": str(e),
            "card_issuer": None,
        }


async def main():
    pdfs = [
        "itau_sem.pdf",
        "fatura-pan.pdf",
        "Fatura_Cartao_Celebre_Elo_Nanquin_01814_23847_66484.pdf",
        "bradesco.pdf",
        "BradescoCartoes09-03-2026-16-01-39.pdf",
        "extratoCartao.pdf",
        "test-fatura.pdf",
        "test-fatura-sem-senha.pdf",
        "backend/test_fatura_santander.pdf",
    ]

    providers = ["google", "mistral"]

    # Filter existing files
    base = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(base, "..", "..")
    existing = []
    for pdf in pdfs:
        full = os.path.normpath(os.path.join(root, "..", pdf))
        if os.path.exists(full):
            existing.append((pdf, full))
        else:
            print(f"⚠️  Não encontrado: {pdf}")

    results = []

    for pdf_name, full_path in existing:
        print(f"\n{'=' * 80}")
        print(f"📄 {pdf_name}")
        print(f"{'=' * 80}")

        for provider in providers:
            print(f"\n  ▶ {provider.upper()}...", end=" ", flush=True)
            r = await test_provider(provider, full_path)
            results.append(r)

            if r["error"]:
                print(f"❌ ERRO ({r['time']:.1f}s): {r['error'][:80]}")
            else:
                diff_str = f"diff=R${r['diff']:.2f}" if r["diff"] is not None else "no total"
                quality = (
                    "✅"
                    if r["diff"] is not None and r["diff"] <= 5
                    else ("⚠️" if r["diff"] is not None and r["diff"] <= 50 else "❓")
                )
                print(
                    f"{quality} {r['items']} items, R${r['items_sum']:.2f}, {diff_str}, ⏱️ {r['time']:.1f}s"
                )

    # Summary table
    print(f"\n\n{'=' * 100}")
    print("📊 RESUMO COMPARATIVO")
    print(f"{'=' * 100}")
    print(
        f"{'Arquivo':<45} {'Provider':<10} {'Items':>6} {'Soma':>12} {'Total':>12} {'Diff':>10} {'Tempo':>8} {'Status'}"
    )
    print(f"{'-' * 45} {'-' * 10} {'-' * 6} {'-' * 12} {'-' * 12} {'-' * 10} {'-' * 8} {'-' * 10}")

    for r in results:
        status = (
            "❌ ERR"
            if r["error"]
            else (
                "✅"
                if r["diff"] is not None and r["diff"] <= 5
                else ("⚠️" if r["diff"] is not None and r["diff"] <= 50 else "❓")
            )
        )
        diff_str = f"R${r['diff']:.2f}" if r["diff"] is not None else "N/A"
        print(
            f"{r['file']:<45} {r['provider']:<10} {r['items']:>6} R${r['items_sum']:>10.2f} R${r['total_fatura']:>10.2f} {diff_str:>10} {r['time']:>6.1f}s {status}"
        )

    # Averages
    print("\n📈 MÉDIAS:")
    for provider in providers:
        pr = [r for r in results if r["provider"] == provider and not r["error"]]
        if pr:
            avg_time = sum(r["time"] for r in pr) / len(pr)
            avg_items = sum(r["items"] for r in pr) / len(pr)
            success = len(pr)
            total = len([r for r in results if r["provider"] == provider])
            print(
                f"  {provider.upper():<10}: tempo médio={avg_time:.1f}s, items médio={avg_items:.0f}, sucesso={success}/{total}"
            )


if __name__ == "__main__":
    asyncio.run(main())
