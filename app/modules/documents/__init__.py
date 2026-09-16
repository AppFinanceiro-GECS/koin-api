"""
Modulo Documents - Processamento de Documentos Financeiros

Este modulo e responsavel pelo upload e processamento de documentos
financeiros (faturas, cupons fiscais, extratos), incluindo:
- Upload e validacao de arquivos (PDF, imagens, CSV, Excel)
- Extracao de dados com LLM Vision (Google Gemini)
- Parser de planilhas (CSV/Excel) de bancos brasileiros
- Deteccao de duplicatas
- Identificacao de parcelamentos

Tipos de documentos suportados:
- fatura_cartao: Faturas de cartao de credito
- cupom_fiscal: Cupons fiscais / notas fiscais
- comprovante: Comprovantes de pagamento
- extrato: Extratos bancarios (CSV/Excel)

Bancos suportados para extratos:
- Nubank, Inter, Itau, Bradesco, Santander, BB, C6, etc.

Dependencias:
- models: Document, DocumentExtraction (centralizados em app.models)
- services: DocumentService, LLMOCRService, SpreadsheetParserService
"""

from app.modules.documents.routers.documents import router
from app.modules.documents.schemas.document import (
    CardInfoResponse,
    DocumentExtractionResponse,
    DocumentResponse,
    ExtractedItemResponse,
    FutureInstallmentResponse,
    InstallmentAnalysisResponse,
)
from app.modules.documents.services.document_service import DocumentService
from app.modules.documents.services.llm_ocr_service import LLMOCRService
from app.modules.documents.services.spreadsheet_parser_service import SpreadsheetParserService

__all__ = [
    # Router
    "router",
    # Schemas
    "FutureInstallmentResponse",
    "ExtractedItemResponse",
    "InstallmentAnalysisResponse",
    "DocumentExtractionResponse",
    "CardInfoResponse",
    "DocumentResponse",
    # Services
    "DocumentService",
    "LLMOCRService",
    "SpreadsheetParserService",
]
