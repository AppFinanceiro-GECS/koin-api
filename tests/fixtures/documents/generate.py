"""Regenerate entirely invented fixtures with the project's PyMuPDF and Pillow.

Run from the repository root: python tests/fixtures/documents/generate.py
No historical documents, external fonts, API calls or personal data are used.
"""

import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

DESTINATION = Path(__file__).resolve().parent
NOTICE = "DOCUMENTO SINTETICO - DADOS INVENTADOS - SEM VALIDADE"
INK = (0.12, 0.16, 0.20)

EXPECTED = {
    "itau_two_columns": {
        "document_type": "fatura_cartao",
        "total_amount": 280.0,
        "items": [
            {
                "description": "LOJA TESTE ORBITA",
                "amount": 120.4,
                "date": "2026-01-15",
                "is_installment": True,
                "installment_current": 3,
                "installment_total": 6,
            },
            {
                "description": "LOJA TESTE NEBULA",
                "amount": 80.1,
                "date": "2026-02-10",
                "is_installment": True,
                "installment_current": 5,
                "installment_total": 10,
            },
            {
                "description": "MERCADO TESTE LUNAR",
                "amount": 54.35,
            },
            {
                "description": "PADARIA TESTE COMETA",
                "amount": 25.15,
            },
        ],
    },
    "nubank": {
        "document_type": "fatura_cartao",
        "total_amount": 150.0,
        "items": [
            {
                "description": "ASSINATURA TESTE QUASAR",
                "amount": 35.9,
                "date": "2025-12-15",
            },
            {
                "description": "LIVRARIA TESTE NOVA",
                "amount": 42.6,
                "date": "2026-02-11",
            },
            {
                "description": "LOJA TESTE PULSAR",
                "amount": 70.0,
                "is_installment": True,
                "installment_current": 2,
                "installment_total": 3,
            },
            {
                "description": "IOF TESTE ESTELAR",
                "amount": 1.5,
            },
        ],
    },
    "bradesco": {
        "document_type": "fatura_cartao",
        "total_amount": 160.0,
        "items": [
            {
                "description": "LOJA TESTE METEORO",
                "amount": 90.5,
                "is_installment": True,
                "installment_current": 4,
                "installment_total": 12,
            },
            {
                "description": "MERCADO TESTE GALAXIA",
                "amount": 64.2,
            },
            {
                "description": "ESTORNO TESTE GALAXIA",
                "amount": -14.2,
            },
            {
                "description": "FARMACIA TESTE AURORA",
                "amount": 19.5,
            },
        ],
    },
    "cupom_fiscal": {
        "document_type": "cupom_fiscal",
        "total_amount": 32.0,
        "items": [
            {
                "description": "ARROZ TESTE ORBITA",
                "amount": 17.3,
            },
            {
                "description": "LEITE TESTE NEBULA",
                "amount": 9.8,
            },
            {
                "description": "SABONETE TESTE COMETA",
                "amount": 4.25,
            },
            {
                "description": "SACOLA TESTE LUNAR",
                "amount": 0.65,
            },
        ],
    },
}


def text(page, x, y, value, size=11, font="helv"):
    page.insert_text((x, y), value, fontsize=size, fontname=font, color=INK)


def page_header(document, bank, number):
    page = document.new_page(width=595, height=842)
    text(page, 36, 35, NOTICE, 9)
    text(page, 36, 78, f"{bank} - FATURA DE TESTE", 19)
    text(page, 36, 110, "Titular: PESSOA FICTICIA ALFA | Cartao de teste final 4242")
    text(page, 36, 132, "Referencia: MARCO/2026 | Vencimento: 12/03/2026")
    page.draw_line((36, 148), (559, 148), color=INK)
    text(page, 36, 806, f"Fixture sintetica de regressao | Pagina {number}", 9)
    return page


def save_pdf(document, name):
    document.set_metadata(
        {
            "title": f"Synthetic test fixture: {name}",
            "author": "Koin synthetic regression fixtures",
            "creationDate": "D:20260101000000Z",
            "modDate": "D:20260101000000Z",
        }
    )
    (DESTINATION / f"{name}.pdf").write_bytes(
        document.tobytes(garbage=4, deflate=True, no_new_id=True)
    )
    document.close()


def generate_itau():
    document = fitz.open()
    page = page_header(document, "Banco Itau / Itaú", 1)
    text(page, 36, 190, "RESUMO DA FATURA", 15)
    text(page, 36, 230, "Total a pagar: R$ 280,00", 17)
    text(page, 36, 268, "Limite total: R$ 5.000,00 | Fechamento: 05/03/2026")
    text(page, 36, 312, "Os lancamentos atuais estao nas DUAS COLUNAS da pagina 2.")
    page = page_header(document, "Banco Itau / Itaú", 2)
    text(page, 36, 188, "LANCAMENTOS ATUAIS - DUAS COLUNAS", 14)
    page.draw_line((295, 214), (295, 405), color=INK)
    for x, title, rows in (
        (
            36,
            "Parcelas de compras anteriores",
            [
                ("15/01 LOJA TESTE ORBITA 03/06", "120,40"),
                ("10/02 LOJA TESTE NEBULA 05/10", "80,10"),
            ],
        ),
        (
            310,
            "Compras do mes atual",
            [
                ("23/02 MERCADO TESTE LUNAR", "54,35"),
                ("26/02 PADARIA TESTE COMETA", "25,15"),
            ],
        ),
    ):
        text(page, x, 224, title, 10)
        text(page, x, 248, "DATA  ESTABELECIMENTO / PARCELA", 9)
        text(page, x + 171, 273, "VALOR (R$)", 9)
        for index, (label, amount) in enumerate(rows):
            y = 307 + index * 55
            text(page, x, y, label, 9)
            text(page, x + 188, y + 19, amount, 11)
    text(page, 36, 448, "Total dos lancamentos atuais: R$ 280,00", 13)
    text(page, 310, 508, "Compras parceladas - proximas faturas", 10)
    text(page, 310, 540, "15/01 LOJA TESTE ORBITA 04/06", 9)
    text(page, 498, 559, "120,40", 11)
    text(page, 310, 590, "10/02 LOJA TESTE NEBULA 06/10", 9)
    text(page, 498, 609, "80,10", 11)
    text(page, 310, 650, "Valores informativos para ABRIL/2026", 9)
    save_pdf(document, "itau_two_columns")


def generate_nubank():
    document = fitz.open()
    page = page_header(document, "Nubank", 1)
    text(page, 36, 185, "FATURA 12 MAR 2026 | Total a pagar: R$ 150,00", 15)
    text(page, 36, 216, "Limite de credito: R$ 4.000,00 | Fechamento: 05/03/2026")
    text(page, 36, 265, "TRANSACOES DA FATURA", 14)
    for index, (label, amount) in enumerate(
        [
            ("15 DEZ ASSINATURA TESTE QUASAR", "35,90"),
            ("11 FEV LIVRARIA TESTE NOVA", "42,60"),
            ("20 FEV LOJA TESTE PULSAR - Parcela 2/3", "70,00"),
            ("24 FEV IOF TESTE ESTELAR", "1,50"),
        ]
    ):
        y = 308 + index * 44
        text(page, 36, y, label, 11)
        text(page, 476, y, f"R$ {amount}", 11)
    text(page, 36, 525, "PAGAMENTOS E FINANCIAMENTOS", 13)
    text(page, 36, 562, "01 MAR Pagamento em 28 FEV - fatura anterior: R$ 600,00")
    text(page, 36, 622, "Total a pagar da fatura atual: R$ 150,00", 14)
    save_pdf(document, "nubank")


def generate_bradesco():
    document = fitz.open()
    page = page_header(document, "Banco Bradesco", 1)
    text(page, 36, 190, "RESUMO DA FATURA", 15)
    text(page, 36, 231, "Compras / Debitos atuais: R$ 174,20")
    text(page, 36, 267, "Estornos atuais: R$ 14,20")
    text(page, 36, 310, "Total a pagar: R$ 160,00", 17)
    text(page, 36, 350, "Limite total: R$ 3.000,00 | Fechamento: 05/03/2026")
    page = page_header(document, "Banco Bradesco", 2)
    text(page, 36, 190, "LANCAMENTOS ATUAIS", 14)
    text(page, 36, 232, "Data    Historico de Lancamentos", 11)
    text(page, 360, 232, "Cidade", 11)
    text(page, 495, 232, "R$", 11)
    for index, (date, label, city, amount) in enumerate(
        [
            ("10/02", "PAG BOLETO BANCARIO", "", "350,00 -"),
            ("05/02", "LOJA TESTE METEORO04/12", "CIDADE TESTE", "90,50"),
            ("12/02", "MERCADO TESTE GALAXIA", "CIDADE TESTE", "64,20"),
            ("23/02", "ESTORNO TESTE GALAXIA", "CIDADE TESTE", "14,20 -"),
            ("25/02", "FARMACIA TESTE AURORA", "CIDADE TESTE", "19,50"),
        ]
    ):
        y = 273 + index * 42
        text(page, 36, y, date, 10)
        text(page, 83, y, label, 10)
        text(page, 360, y, city, 9)
        text(page, 495, y, amount, 10)
    text(page, 36, 522, "Total para PESSOA FICTICIA ALFA: R$ 160,00", 13)
    text(page, 36, 583, "Total parcelados para proximas faturas: R$ 999,90")
    save_pdf(document, "bradesco")


def generate_cupom():
    image = Image.new("RGB", (1100, 1100), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=25)
    heading = ImageFont.load_default(size=34)
    lines = [
        NOTICE,
        "CUPOM FISCAL ELETRONICO - NFC-e",
        "MERCADO FICTICIO CONSTELACAO",
        "Data da compra: 04/03/2026 10:15:00",
        "ITEM  DESCRICAO                    QTD UN   VL TOTAL",
        "001   ARROZ TESTE ORBITA             1 UN      17,30",
        "002   LEITE TESTE NEBULA             2 UN       9,80",
        "003   SABONETE TESTE COMETA          1 UN       4,25",
        "004   SACOLA TESTE LUNAR             1 UN       0,65",
        "QUANTIDADE DE ITENS: 4",
        "TOTAL A PAGAR: R$ 32,00",
        "FORMA DE PAGAMENTO: PIX R$ 32,00",
        "DOCUMENTO DE TESTE - NAO E DOCUMENTO FISCAL VALIDO",
    ]
    for index, line in enumerate(lines):
        y = 42 + index * 74
        draw.text((32, y), line, fill="black", font=heading if index in {1, 10} else font)
    image.save(DESTINATION / "cupom_fiscal.png")


def main():
    generate_itau()
    generate_nubank()
    generate_bradesco()
    generate_cupom()
    for name, expected in EXPECTED.items():
        (DESTINATION / f"{name}.expected.json").write_text(
            json.dumps(expected, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
