"""Classe base abstrata para providers de LLM"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Interface base para todos os providers de LLM"""

    def __init__(self, model: str | None = None):
        self.model = model

    @abstractmethod
    async def extract_from_image(self, image_content: bytes, mime_type: str) -> dict:
        """Extrai dados de uma imagem usando visao do LLM

        Args:
            image_content: Conteudo binario da imagem
            mime_type: Tipo MIME (image/png, image/jpeg, etc.)

        Returns:
            Dict com 'items', 'card_info', 'document_type' ou 'error'
        """
        pass

    @abstractmethod
    async def extract_from_pdf(
        self, pdf_content: bytes, filename: str = "document.pdf", password: str | None = None
    ) -> dict:
        """Extrai dados de um PDF

        Args:
            pdf_content: Conteudo binario do PDF
            filename: Nome do arquivo
            password: Senha do PDF (opcional)

        Returns:
            Dict com 'items', 'card_info', 'document_type' ou 'error'
        """
        pass

    def _is_retryable_error(self, error: Exception) -> bool:
        """Verifica se o erro permite retry (503, 429, etc.)"""
        error_str = str(error).lower()
        return any(
            code in error_str
            for code in [
                "503",
                "429",
                "unavailable",
                "overloaded",
                "rate limit",
                "resource_exhausted",
            ]
        )
