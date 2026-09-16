"""Extrator de texto estruturado de PDFs preservando layout de colunas"""

import fitz  # PyMuPDF


class PDFTextExtractor:
    """Extrai texto de PDFs preservando layout de colunas"""

    @staticmethod
    def extract_text_with_layout(pdf_bytes: bytes, password: str | None = None) -> str:
        """
        Extrai texto do PDF preservando layout de colunas.

        Args:
            pdf_bytes: Conteúdo binário do PDF
            password: Senha do PDF (opcional)

        Returns:
            Texto extraído com layout preservado
        """
        try:
            # Abrir PDF
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

            # Descriptografar se necessário
            if pdf_document.is_encrypted:
                if password:
                    if not pdf_document.authenticate(password):
                        raise ValueError("Senha incorreta")
                else:
                    raise ValueError("PDF requer senha")

            all_text = []

            # Processar cada página
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]

                # Extrair texto com layout preservado
                # sort=True mantém a ordem de leitura correta (esquerda→direita, top→bottom)
                text = page.get_text("text", sort=True)

                if text.strip():
                    all_text.append(f"=== PÁGINA {page_num + 1} ===\n{text}")

            pdf_document.close()

            return "\n\n".join(all_text)

        except Exception as e:
            print(f"[PDFTextExtractor] Erro ao extrair texto: {e}")
            return ""

    @staticmethod
    def extract_text_blocks_with_positions(
        pdf_bytes: bytes, password: str | None = None
    ) -> list[dict]:
        """
        Extrai blocos de texto com suas posições (x, y).
        Útil para identificar colunas baseado na posição horizontal.

        Returns:
            Lista de dicts com {text, x, y, page}
        """
        try:
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

            if pdf_document.is_encrypted:
                if password:
                    if not pdf_document.authenticate(password):
                        raise ValueError("Senha incorreta")
                else:
                    raise ValueError("PDF requer senha")

            all_blocks = []

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]

                # Extrair blocos de texto com posições
                blocks = page.get_text("dict")["blocks"]

                for block in blocks:
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            text = " ".join([span["text"] for span in line.get("spans", [])])
                            if text.strip():
                                all_blocks.append(
                                    {
                                        "text": text.strip(),
                                        "x": line["bbox"][0],  # x0
                                        "y": line["bbox"][1],  # y0
                                        "page": page_num + 1,
                                    }
                                )

            pdf_document.close()

            return all_blocks

        except Exception as e:
            print(f"[PDFTextExtractor] Erro ao extrair blocos: {e}")
            return []
