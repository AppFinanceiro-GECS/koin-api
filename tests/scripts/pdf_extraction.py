#!/usr/bin/env python3
"""Test script para processar um PDF e debugar a extração."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Carregar .env
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path


async def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "../itau_sem.pdf"
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        # Tentar no diretório do projeto
        pdf_path = Path(__file__).parent.parent / "itau_sem.pdf"

    if not pdf_path.exists():
        print(f"PDF não encontrado: {pdf_path}")
        return

    print(f"=== Processando: {pdf_path} ===")
    print(f"Tamanho: {pdf_path.stat().st_size} bytes")

    with open(pdf_path, "rb") as f:
        pdf_content = f.read()

    from app.modules.documents.services.llm_ocr_service import LLMOCRService

    service = LLMOCRService(provider="google")

    print("\n--- Iniciando extração ---")
    result = await service.extract_from_image(
        pdf_content, mime_type="application/pdf", filename=pdf_path.name
    )

    # Mostrar OCR text se disponível
    ocr_text = result.pop("_ocr_text", None)
    result.pop("_ocr_text_preview", None)

    if ocr_text:
        print(f"\n=== OCR TEXT ({len(ocr_text)} chars) ===")
        print(ocr_text[:3000])
        print("..." if len(ocr_text) > 3000 else "")

        # Verificar se MOTOCHEFE está no OCR text
        print("\n=== BUSCA POR MOTOCHEFE NO OCR TEXT ===")
        motochefe_idx = ocr_text.upper().find("MOTOCHEFE")
        if motochefe_idx >= 0:
            start = max(0, motochefe_idx - 100)
            end = min(len(ocr_text), motochefe_idx + 100)
            print(f"ENCONTRADO na posição {motochefe_idx}:")
            print(f"  ...{ocr_text[start:end]}...")
        else:
            print("NÃO ENCONTRADO no OCR text!")

        # Verificar seções
        print("\n=== SEÇÕES DO OCR TEXT ===")
        for marker in [
            "lançamentos",
            "lancamentos",
            "compras e saques",
            "produtos e serviços",
            "próximas faturas",
            "proximas faturas",
            "total dos lançamentos",
            "total dos lancamentos",
            "compras parceladas",
        ]:
            idx = ocr_text.lower().find(marker)
            if idx >= 0:
                context = ocr_text[max(0, idx - 10) : idx + len(marker) + 30].replace("\n", "\\n")
                print(f"  '{marker}' na pos {idx}: ...{context}...")

        # Buscar todos os valores 574 no OCR
        print("\n=== BUSCA POR 574 NO OCR TEXT ===")
        search_pos = 0
        while True:
            idx = ocr_text.find("574", search_pos)
            if idx < 0:
                break
            start = max(0, idx - 50)
            end = min(len(ocr_text), idx + 20)
            print(f"  pos {idx}: ...{ocr_text[start:end].replace(chr(10), ' ')}...")
            search_pos = idx + 1

    # Mostrar resultado
    print("\n=== RESULTADO ===")
    print(f"document_type: {result.get('document_type')}")
    print(f"error: {result.get('error')}")

    card_info = result.get("card_info", {})
    if card_info:
        print("\ncard_info:")
        print(f"  issuer: {card_info.get('card_issuer')}")
        print(f"  total_amount: {card_info.get('total_amount')}")
        print(f"  invoice: {card_info.get('invoice_month')}/{card_info.get('invoice_year')}")

    items = result.get("items", [])
    print(f"\n=== ITEMS ({len(items)}) ===")
    items_sum = 0
    for i, item in enumerate(items):
        amt = item.get("amount", 0)
        items_sum += amt if amt > 0 else 0
        installment = ""
        if item.get("is_installment"):
            installment = f" [{item.get('installment_current')}/{item.get('installment_total')}]"
        card_digits = (
            f" [card:{item.get('card_last_digits')}]" if item.get("card_last_digits") else ""
        )
        print(
            f"  {i + 1:2}. {item.get('description', ''):35} R$ {amt:>8.2f}  {item.get('date', ''):10}{installment}{card_digits}"
        )

    total = card_info.get("total_amount", 0) if card_info else 0
    diff = total - items_sum
    print("\n=== SOMA ===")
    print(f"  Items sum:    R$ {items_sum:.2f}")
    print(f"  Total fatura: R$ {total:.2f}")
    print(f"  Diferença:    R$ {diff:.2f}")
    if abs(diff) > 1:
        print("  ⚠️ DIFERENÇA SIGNIFICATIVA!")
    else:
        print("  ✅ SOMA OK!")


if __name__ == "__main__":
    asyncio.run(main())
