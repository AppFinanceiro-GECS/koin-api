"""Test extraction fixes with real PDFs via Mistral pipeline."""

import asyncio
import os
import sys

# Setup environment
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

# Load .env
from dotenv import load_dotenv

load_dotenv()


async def test_pdf(filepath: str):
    from app.modules.documents.services.llm_ocr_service import LLMOCRService

    service = LLMOCRService(provider="mistral")

    with open(filepath, "rb") as f:
        content = f.read()

    filename = os.path.basename(filepath)
    print(f"\n{'=' * 80}")
    print(f"TESTANDO: {filename} ({len(content)} bytes)")
    print(f"{'=' * 80}")

    result = await service.extract_from_image(
        image_content=content,
        mime_type="application/pdf",
        filename=filename,
    )

    if result.get("error"):
        print(f"\n❌ ERRO: {result['error']}")
        return

    items = result.get("items", [])
    card_info = result.get("card_info", {})

    print("\n📋 CARD INFO:")
    print(f"  Emissor: {card_info.get('card_issuer')}")
    print(f"  Bandeira: {card_info.get('card_brand')}")
    print(f"  Nome: {card_info.get('card_name')}")
    print(f"  Últimos dígitos: {card_info.get('card_last_digits')}")
    print(f"  Mês/Ano fatura: {card_info.get('invoice_month')}/{card_info.get('invoice_year')}")
    print(f"  Fechamento: {card_info.get('closing_date')}")
    print(f"  Vencimento: {card_info.get('due_date')}")
    print(f"  Total: R$ {card_info.get('total_amount')}")

    print(f"\n📊 ITENS EXTRAÍDOS ({len(items)}):")
    total_positivo = 0
    total_negativo = 0
    for i, item in enumerate(items, 1):
        amt = item.get("amount", 0)
        if amt > 0:
            total_positivo += amt
        else:
            total_negativo += amt

        inst = ""
        if item.get("is_installment"):
            inst = f" [{item.get('installment_current')}/{item.get('installment_total')}]"

        print(
            f"  {i:2d}. {item.get('date', '?'):10s} {item.get('description', '?')[:40]:40s} R$ {amt:>10.2f}{inst}"
        )

    total_amount = card_info.get("total_amount", 0)
    diff = total_positivo + total_negativo - total_amount if total_amount else 0

    print("\n📈 VALIDAÇÃO:")
    print(f"  Soma positivos: R$ {total_positivo:.2f}")
    print(f"  Soma negativos: R$ {total_negativo:.2f}")
    print(f"  Soma total:     R$ {total_positivo + total_negativo:.2f}")
    print(f"  Total fatura:   R$ {total_amount:.2f}")
    print(f"  Diferença:      R$ {diff:.2f}")
    if abs(diff) <= 5:
        print("  ✅ SOMA CORRETA!")
    elif abs(diff) <= 50:
        print("  ⚠️ SOMA PRÓXIMA (diff < R$50)")
    else:
        print("  ❌ SOMA DIVERGENTE!")

    return result


async def main():
    pdfs = [
        "../itau_sem.pdf",
        "../fatura-pan.pdf",
        "../Fatura_Cartao_Celebre_Elo_Nanquin_01814_23847_66484.pdf",
    ]

    for pdf in pdfs:
        filepath = os.path.join(os.path.dirname(__file__), pdf)
        if os.path.exists(filepath):
            await test_pdf(filepath)
        else:
            print(f"\n⚠️ Arquivo não encontrado: {pdf}")


if __name__ == "__main__":
    asyncio.run(main())
