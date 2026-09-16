#!/usr/bin/env python3
"""Test script para ver o OCR text completo do Bradesco."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from pathlib import Path


async def main():
    pdf_path = Path(__file__).parent.parent / "bradesco.pdf"
    if not pdf_path.exists():
        print(f"PDF não encontrado: {pdf_path}")
        return

    print(f"=== Processando: {pdf_path} ===")

    with open(pdf_path, "rb") as f:
        pdf_content = f.read()

    from app.modules.documents.services.providers.mistral_provider import MistralProvider

    provider = MistralProvider()

    # Fazer upload + OCR
    print("\n--- OCR ---")
    from app.modules.documents.services.providers.mistral_provider import get_mistral_client

    client = await get_mistral_client()
    uploaded = provider._upload_sync(client, pdf_content, "bradesco.pdf")
    print(f"Upload: {uploaded.id}")
    import asyncio

    ocr_result = await asyncio.to_thread(provider._ocr_sync, client, uploaded.id)
    ocr_text = "\n\n".join(page.markdown for page in ocr_result.pages if page.markdown)

    print(f"\n=== OCR TEXT COMPLETO ({len(ocr_text)} chars) ===")
    print(ocr_text)
    print("=== FIM OCR TEXT ===")


if __name__ == "__main__":
    asyncio.run(main())
