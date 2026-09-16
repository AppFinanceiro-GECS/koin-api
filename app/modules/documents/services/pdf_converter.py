"""Conversor de PDF para imagens"""

import asyncio


class PasswordRequiredException(Exception):
    """Raised when PDF requires password"""

    pass


def check_pdf_needs_password(pdf_content: bytes) -> bool:
    """Quick check if PDF requires password without full processing

    Args:
        pdf_content: PDF file content as bytes

    Returns:
        bool: True if PDF requires password, False otherwise
    """
    try:
        import fitz

        pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
        needs_pass = pdf_doc.needs_pass
        pdf_doc.close()
        return needs_pass
    except Exception:
        return False


def convert_pdf_to_images_sync(
    pdf_content: bytes, password: str | None = None
) -> tuple[list[tuple[bytes, str]], str | None]:
    """Converte PDF para lista de imagens (uma por pagina) - SINCRONO

    Args:
        pdf_content: PDF file content as bytes
        password: Optional password to unlock protected PDF

    Returns:
        Tuple of (images list, error message or None)

    Raises:
        PasswordRequiredException: If PDF requires password and none provided
    """
    try:
        import fitz  # pymupdf

        images = []
        pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")

        # Check if password is required
        if pdf_doc.needs_pass:
            if password is None:
                pdf_doc.close()
                raise PasswordRequiredException("PDF protegido por senha")

            # Try to authenticate with provided password
            auth_result = pdf_doc.authenticate(password)
            if auth_result == 0:
                pdf_doc.close()
                return [], "Senha incorreta"

        if len(pdf_doc) == 0:
            pdf_doc.close()
            return [], "PDF nao contem paginas"

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            # Renderizar pagina como imagem com boa resolucao
            mat = fitz.Matrix(
                1.5, 1.5
            )  # 1.5x zoom - boa qualidade para OCR com menor uso de memória
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            images.append((img_bytes, "image/png"))

            # Liberar memória da página imediatamente após processá-la
            del pix
            del page

        pdf_doc.close()
        return images, None

    except ImportError as e:
        return [], f"PyMuPDF nao instalado: {e}"
    except Exception as e:
        return [], f"Erro ao converter PDF: {e}"


async def convert_pdf_to_images(
    pdf_content: bytes, password: str | None = None
) -> tuple[list[tuple[bytes, str]], str | None]:
    """Converte PDF para lista de imagens (uma por pagina) - ASYNC wrapper

    Executa em thread separada para nao bloquear o event loop.

    Args:
        pdf_content: PDF file content as bytes
        password: Optional password to unlock protected PDF

    Returns:
        Tuple of (images list, error message or None)

    Raises:
        PasswordRequiredException: If PDF requires password and none provided
    """
    return await asyncio.to_thread(convert_pdf_to_images_sync, pdf_content, password)
