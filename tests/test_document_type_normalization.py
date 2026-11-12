from datetime import datetime

import pytest

from app.models.document import DocumentStatus, DocumentType
from app.modules.documents.schemas.document import DocumentResponse


def test_document_type_from_string_valid_and_variants():
    # Direct enum strings
    assert DocumentType.from_string("receipt") == DocumentType.RECEIPT
    assert DocumentType.from_string("invoice") == DocumentType.INVOICE
    assert DocumentType.from_string("statement") == DocumentType.STATEMENT
    assert DocumentType.from_string("cupom_fiscal") == DocumentType.CUPOM_FISCAL
    assert DocumentType.from_string("fatura_cartao") == DocumentType.FATURA_CARTAO
    assert DocumentType.from_string("comprovante") == DocumentType.COMPROVANTE
    assert DocumentType.from_string("comprovante_pix") == DocumentType.COMPROVANTE_PIX
    assert DocumentType.from_string("extrato") == DocumentType.EXTRATO
    assert DocumentType.from_string("extrato_bancario") == DocumentType.EXTRATO_BANCARIO
    assert DocumentType.from_string("nota_fiscal") == DocumentType.NOTA_FISCAL
    assert DocumentType.from_string("boleto") == DocumentType.BOLETO
    assert DocumentType.from_string("unknown") == DocumentType.UNKNOWN


def test_document_type_from_string_heuristics():
    # Heuristics
    assert DocumentType.from_string("comprovante_transferencia_pix") == DocumentType.COMPROVANTE_PIX
    assert DocumentType.from_string("pix_pagamento") == DocumentType.COMPROVANTE_PIX
    assert DocumentType.from_string("fatura_inter") == DocumentType.FATURA_CARTAO
    assert DocumentType.from_string("fatura de cartao") == DocumentType.FATURA_CARTAO
    assert DocumentType.from_string("cupom") == DocumentType.CUPOM_FISCAL
    assert DocumentType.from_string("recibo_aluguel") == DocumentType.COMPROVANTE
    assert DocumentType.from_string("extrato_cc") == DocumentType.EXTRATO
    assert DocumentType.from_string("danfe_nfe") == DocumentType.NOTA_FISCAL
    assert DocumentType.from_string("boleto_bancario") == DocumentType.BOLETO


def test_document_type_from_string_edge_cases():
    assert DocumentType.from_string(None) == DocumentType.UNKNOWN
    assert DocumentType.from_string("") == DocumentType.UNKNOWN
    assert DocumentType.from_string("random_gibberish_12345") == DocumentType.UNKNOWN
    assert DocumentType.from_string(DocumentType.COMPROVANTE_PIX) == DocumentType.COMPROVANTE_PIX


@pytest.mark.parametrize(
    "raw_type, expected_enum",
    [
        ("comprovante_pix", DocumentType.COMPROVANTE_PIX),
        ("COMPROVANTE_PIX", DocumentType.COMPROVANTE_PIX),
        ("comprovante_transferencia", DocumentType.COMPROVANTE),
        ("fatura_cartao", DocumentType.FATURA_CARTAO),
        ("cupom_fiscal", DocumentType.CUPOM_FISCAL),
        ("extrato_bancario", DocumentType.EXTRATO_BANCARIO),
        ("extrato", DocumentType.EXTRATO),
        ("nota_fiscal", DocumentType.NOTA_FISCAL),
        ("boleto", DocumentType.BOLETO),
        ("unrecognized_document_type", DocumentType.UNKNOWN),
        (None, None),
    ],
)
def test_document_response_validation_never_fails(raw_type, expected_enum):
    data = {
        "id": 1,
        "file_hash": "a" * 64,
        "original_filename": "test.pdf",
        "mime_type": "application/pdf",
        "status": DocumentStatus.COMPLETED,
        "document_type": raw_type,
        "error_message": None,
        "created_at": datetime.now(),
        "processed_at": datetime.now(),
    }
    response = DocumentResponse.model_validate(data)
    assert response.document_type == expected_enum
