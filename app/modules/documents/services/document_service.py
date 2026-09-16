from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker
from app.core.utils import utc_now
from app.models.credit_card import CreditCard
from app.models.document import Document, DocumentStatus
from app.models.transaction import Transaction
from app.models.user import User


class PasswordRequiredError(Exception):
    """Special error for inline password request - not a failure"""

    pass


def _write_file_sync(file_path: Path, content: bytes) -> None:
    """Escrita sincrona de arquivo - para uso com asyncio.to_thread"""
    with open(file_path, "wb") as f:
        f.write(content)


def _read_file_sync(file_path: str) -> bytes:
    """Leitura sincrona de arquivo - para uso com asyncio.to_thread"""
    with open(file_path, "rb") as f:
        return f.read()


async def process_document_background(
    document_id: int,
    user_id: int,
    file_path: str,
    mime_type: str,
    filename: str,
    password: str | None = None,
):
    """
    Processa documento em background (fora do request context).
    Cria sua propria sessao do banco.
    Recebe file_path ao inves de bytes para economizar memoria.

    Args:
        document_id: Document ID
        user_id: User ID
        file_path: Path to file on disk
        mime_type: MIME type
        filename: Original filename
        password: Optional password for protected PDFs
    """
    import gc

    print(f"[DOC_BG] Iniciando processamento background: document_id={document_id}")

    file_bytes = None
    try:
        # Ler arquivo do disco (em thread para nao bloquear)
        file_bytes = await asyncio.to_thread(_read_file_sync, file_path)
        print(f"[DOC_BG] Arquivo lido: {len(file_bytes)} bytes")
    except Exception as e:
        print(f"[DOC_BG] Erro ao ler arquivo {file_path}: {e}")
        async with async_session_maker() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document:
                document.status = DocumentStatus.FAILED
                document.error_message = f"Erro ao ler arquivo: {e}"
                await db.commit()
        return

    async with async_session_maker() as db:
        try:
            # Buscar documento
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()

            if not document:
                print(f"[DOC_BG] Documento {document_id} nao encontrado")
                return

            # Buscar usuario
            from app.models.user import User

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                print(f"[DOC_BG] Usuario {user_id} nao encontrado")
                document.status = DocumentStatus.FAILED
                document.error_message = "Usuario nao encontrado"
                await db.commit()
                return

            # Processar documento
            document.status = DocumentStatus.PROCESSING
            await db.commit()

            from app.modules.documents.services.llm_ocr_service import LLMOCRService

            if settings.mistral_api_key:
                llm_service = LLMOCRService(provider="mistral", model=settings.mistral_llm_model)
            else:
                llm_service = LLMOCRService(
                    provider="google", model=settings.vision_model or "gemini-2.0-flash"
                )

            extraction_data = await llm_service.extract_from_image(
                file_bytes, mime_type, filename=filename, password=password
            )

            # Verificar se houve erro
            if extraction_data is None or extraction_data.get("error"):
                document.status = DocumentStatus.FAILED
                document.error_message = (
                    extraction_data.get("error") if extraction_data else "Extracao falhou"
                )
                print(f"[DOC_BG] Documento {document_id} falhou: {document.error_message}")
            else:
                # Validar se a soma dos itens bate com o total da fatura
                if extraction_data.get("document_type") == "fatura_cartao":
                    total_amount = extraction_data.get("card_info", {}).get("total_amount")
                    items = extraction_data.get("items", [])

                    if total_amount and items:
                        items_sum = sum(item.get("amount", 0) for item in items)
                        difference = abs(total_amount - items_sum)

                        print(
                            f"[DOC_BG] Validação de soma: total_fatura=R$ {total_amount:.2f}, soma_items=R$ {items_sum:.2f}, diff=R$ {difference:.2f}"
                        )

                        # Se diferença > R$ 50, há itens faltando ou sobrando
                        if difference > 50:
                            print(f"[DOC_BG] ⚠️ ALERTA: Diferença de R$ {difference:.2f} detectada!")
                            print(
                                "[DOC_BG] Possível causa: LLM ignorou alguma coluna/seção de transações"
                            )
                            # Adicionar flag nos extracted_data para o frontend alertar o usuário
                            extraction_data["validation_warning"] = {
                                "type": "sum_mismatch",
                                "expected": total_amount,
                                "actual": items_sum,
                                "difference": difference,
                                "message": f"A soma das transações (R$ {items_sum:.2f}) não bate com o total da fatura (R$ {total_amount:.2f}). Diferença: R$ {difference:.2f}",
                            }

                document.status = DocumentStatus.COMPLETED
                document.document_type = extraction_data.get("document_type")
                # Salvar dados extraidos para recuperacao posterior
                document.extracted_data = extraction_data
                print(
                    f"[DOC_BG] Documento {document_id} processado com sucesso: {len(extraction_data.get('items', []))} itens"
                )

            document.processed_at = utc_now()
            await db.commit()

        except Exception as e:
            print(f"[DOC_BG] Erro ao processar documento {document_id}: {e}")
            import traceback

            traceback.print_exc()

            try:
                result = await db.execute(select(Document).where(Document.id == document_id))
                document = result.scalar_one_or_none()
                if document:
                    document.status = DocumentStatus.FAILED
                    document.error_message = str(e)
                    await db.commit()
            except Exception:
                pass

        finally:
            # Cleanup explicito para liberar memoria
            del file_bytes
            gc.collect()


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_async(
        self,
        user: User,
        file: UploadFile,
        background_tasks: BackgroundTasks,
        password: str | None = None,
        credit_card_id: int | None = None,
    ) -> dict:
        """
        Upload async: retorna imediatamente e processa em background.
        Retorna dict com id, status e message.

        Args:
            user: Current user
            file: Uploaded file
            background_tasks: FastAPI background tasks
            password: Optional password for protected PDFs
            credit_card_id: Optional credit card ID to fetch saved password
        """
        from app.modules.documents.schemas.document import DocumentAsyncUploadResponse

        # Validar extensao
        ext = file.filename.split(".")[-1].lower() if file.filename else ""
        if ext not in settings.allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Extensao nao permitida. Use: {', '.join(settings.allowed_extensions)}",
            )

        # Validar tamanho ANTES de ler o conteudo (economia de memoria)
        file.file.seek(0, 2)  # Vai para o final
        file_size = file.file.tell()
        file.file.seek(0)  # Volta para o início

        max_size = settings.max_upload_size_mb * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Arquivo muito grande. Maximo: {settings.max_upload_size_mb}MB",
            )

        # Ler conteudo (tamanho já validado)
        content = await file.read()

        # Check if PDF requires password
        is_pdf = file.filename and file.filename.lower().endswith(".pdf")
        if is_pdf:
            from app.modules.documents.services.pdf_converter import check_pdf_needs_password

            needs_password = check_pdf_needs_password(content)

            if needs_password and password is None:
                # Try to get password from credit card if provided
                if credit_card_id:
                    result = await self.db.execute(
                        select(CreditCard).where(
                            CreditCard.id == credit_card_id, CreditCard.user_id == user.id
                        )
                    )
                    card = result.scalar_one_or_none()

                    if card and card.invoice_password_encrypted:
                        from app.core.crypto import decrypt_password

                        try:
                            password = decrypt_password(card.invoice_password_encrypted)
                            print(
                                f"[DOC_SVC_ASYNC] Using saved password from credit card {credit_card_id}"
                            )
                        except Exception as e:
                            print(f"[DOC_SVC_ASYNC] Failed to decrypt password: {e}")

                # If still no password, raise special error
                if password is None:
                    raise PasswordRequiredError("PDF protegido por senha")

        # Calcular hash para dedupe
        file_hash = hashlib.sha256(content).hexdigest()

        # Salvar arquivo
        upload_dir = Path(settings.upload_dir) / str(user.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / f"{file_hash}.{ext}"
        await asyncio.to_thread(_write_file_sync, file_path, content)

        # Guardar tamanho antes de limpar content
        content_size = len(content)

        # Criar registro com status PROCESSING
        document = Document(
            user_id=user.id,
            file_path=str(file_path),
            file_hash=file_hash,
            file_size=content_size,
            mime_type=file.content_type or f"application/{ext}",
            original_filename=file.filename or "unknown",
            status=DocumentStatus.PROCESSING,  # Ja marca como processing
        )
        self.db.add(document)
        await self.db.flush()
        await self.db.refresh(document)

        # Limpar content da memoria - arquivo ja esta no disco
        del content

        # Agendar processamento em background (passa file_path ao inves de bytes)
        background_tasks.add_task(
            process_document_background,
            document.id,
            user.id,
            str(file_path),  # Passa path ao inves de bytes para economizar memoria
            file.content_type or f"application/{ext}",
            file.filename or "unknown",
            password,  # Pass password to background task
        )

        print(f"[DOC_SVC] Upload async agendado: document_id={document.id}")

        return DocumentAsyncUploadResponse(
            id=document.id,
            status=DocumentStatus.PROCESSING,
            message="Documento enviado. Processamento em andamento.",
        )

    async def upload(
        self,
        user: User,
        file: UploadFile,
        password: str | None = None,
        credit_card_id: int | None = None,
    ) -> Document:
        # Validar extensao
        ext = file.filename.split(".")[-1].lower() if file.filename else ""
        if ext not in settings.allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Extensao nao permitida. Use: {', '.join(settings.allowed_extensions)}",
            )

        # Validar tamanho ANTES de ler o conteudo (economia de memoria)
        file.file.seek(0, 2)  # Vai para o final
        file_size = file.file.tell()
        file.file.seek(0)  # Volta para o início

        max_size = settings.max_upload_size_mb * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Arquivo muito grande. Maximo: {settings.max_upload_size_mb}MB",
            )

        # Ler conteudo (tamanho já validado)
        content = await file.read()

        # Check if PDF requires password
        is_pdf = file.filename and file.filename.lower().endswith(".pdf")
        if is_pdf:
            from app.modules.documents.services.pdf_converter import check_pdf_needs_password

            needs_password = check_pdf_needs_password(content)

            if needs_password and password is None:
                # Try to get password from credit card if provided
                if credit_card_id:
                    result = await self.db.execute(
                        select(CreditCard).where(
                            CreditCard.id == credit_card_id, CreditCard.user_id == user.id
                        )
                    )
                    card = result.scalar_one_or_none()

                    if card and card.invoice_password_encrypted:
                        from app.core.crypto import decrypt_password

                        try:
                            password = decrypt_password(card.invoice_password_encrypted)
                            print(
                                f"[DOC_SVC] Using saved password from credit card {credit_card_id}"
                            )
                        except Exception as e:
                            print(f"[DOC_SVC] Failed to decrypt password: {e}")
                            # Password might be invalid, will raise PasswordRequiredError below

                # If still no password, raise special error
                if password is None:
                    raise PasswordRequiredError("PDF protegido por senha")

        # Calcular hash para dedupe
        file_hash = hashlib.sha256(content).hexdigest()

        # Verificar se e duplicata (apenas informativo)
        existing_result = await self.db.execute(
            select(Document)
            .where(
                Document.user_id == user.id,
                Document.file_hash == file_hash,
            )
            .limit(1)
        )
        existing_document = existing_result.scalar_one_or_none()
        is_duplicate = existing_document is not None

        if is_duplicate:
            print(
                f"[DOC_SVC] Duplicate detected (informative only): existing_id={existing_document.id}"
            )

        # Salvar arquivo
        upload_dir = Path(settings.upload_dir) / str(user.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / f"{file_hash}.{ext}"
        # Escrita em thread separada para nao bloquear o event loop
        await asyncio.to_thread(_write_file_sync, file_path, content)

        # Criar registro
        document = Document(
            user_id=user.id,
            file_path=str(file_path),
            file_hash=file_hash,
            file_size=len(content),
            mime_type=file.content_type or f"application/{ext}",
            original_filename=file.filename or "unknown",
            status=DocumentStatus.PENDING,
        )
        self.db.add(document)
        await self.db.flush()
        await self.db.refresh(document)

        # Processar documento e extrair dados (sem salvar extracao)
        extraction_data = await self._process_document(document, content, password)

        # Retornar resposta com flag de duplicata e itens extraidos (nao salvos)
        from app.modules.documents.schemas.document import (
            CardInfoResponse,
            DocumentResponse,
            ExtractedItemResponse,
        )

        response = DocumentResponse.model_validate(document)
        response.is_duplicate = is_duplicate

        # Converter itens extraidos para o formato de resposta e verificar duplicados
        if extraction_data and extraction_data.get("items"):
            # Detectar recorrencias (Netflix, Spotify, etc.)
            from app.modules.known_services.services.recurring_detector import (
                RecurringDetectorService,
            )

            recurring_detector = RecurringDetectorService(self.db)

            card_info = extraction_data.get("card_info", {})
            invoice_month = card_info.get("invoice_month") if card_info else None
            invoice_year = card_info.get("invoice_year") if card_info else None

            items_with_detection = await recurring_detector.detect_all(
                user=user,
                items=extraction_data["items"],
                invoice_month=invoice_month,
                invoice_year=invoice_year,
            )

            # Filtrar itens com valor != 0
            valid_items = [item for item in items_with_detection if item.get("amount", 0) != 0]

            # Verificar duplicatas em batch (1 query)
            items_for_dup_check = [
                (item.get("description", "Item"), item.get("amount", 0), item.get("date"))
                for item in valid_items
            ]
            duplicate_results = await self._check_duplicates_batch(user, items_for_dup_check)

            extracted_items = []
            for idx, item in enumerate(valid_items):
                duplicate_info = (
                    duplicate_results[idx]
                    if idx < len(duplicate_results)
                    else {"is_duplicate": False, "transaction_id": None}
                )

                # Converter future_installments se existir
                future_installments = None
                if item.get("future_installments"):
                    from app.modules.documents.schemas.document import FutureInstallmentResponse

                    future_installments = [
                        FutureInstallmentResponse(
                            installment=fi.get("installment"),
                            reference_month=fi.get("reference_month"),
                            reference_year=fi.get("reference_year"),
                        )
                        for fi in item["future_installments"]
                        if fi.get("installment")
                        and fi.get("reference_month")
                        and fi.get("reference_year")
                    ]

                # Converter recurring_detection se existir
                recurring_detection = None
                if item.get("recurring_detection"):
                    from app.modules.known_services.schemas.recurring_detection import (
                        RecurringDetection,
                    )

                    recurring_detection = RecurringDetection(**item["recurring_detection"])

                extracted_items.append(
                    ExtractedItemResponse(
                        description=item.get("description", "Item"),
                        amount=item.get("amount", 0),
                        date=item.get("date"),
                        category=item.get("category"),
                        confidence=item.get("confidence", 0.9),
                        transaction_type=item.get("transaction_type"),  # Tipo extraido pelo LLM
                        is_installment=item.get("is_installment", False),
                        installment_current=item.get("installment_current"),
                        installment_total=item.get("installment_total"),
                        future_installments=future_installments if future_installments else None,
                        is_duplicate=duplicate_info["is_duplicate"],
                        existing_transaction_id=duplicate_info.get("transaction_id"),
                        recurring_detection=recurring_detection,
                        # Campos para cupom fiscal (grocery tracking)
                        quantity=item.get("quantity"),
                        unit=item.get("unit"),
                        unit_price=item.get("unit_price"),
                        grocery_category=item.get("grocery_category"),
                        necessity_type=item.get("necessity_type"),
                    )
                )

            response.extracted_items = extracted_items

        # Incluir informacoes do cartao (para faturas)
        if extraction_data and extraction_data.get("card_info"):
            card_info = extraction_data["card_info"]
            response.card_info = CardInfoResponse(
                card_issuer=card_info.get("card_issuer"),
                card_bank=card_info.get("card_bank"),
                card_brand=card_info.get("card_brand"),
                card_partner=card_info.get("card_partner"),
                card_last_digits=card_info.get("card_last_digits"),
                card_name=card_info.get("card_name"),
                invoice_month=card_info.get("invoice_month"),
                invoice_year=card_info.get("invoice_year"),
                closing_date=card_info.get("closing_date"),
                closing_day=card_info.get("closing_day"),
                due_date=card_info.get("due_date"),
                due_day=card_info.get("due_day"),
                total_amount=card_info.get("total_amount"),
                credit_limit=card_info.get("credit_limit"),
                credit_used=card_info.get("credit_used"),
                credit_available=card_info.get("credit_available"),
            )

        # Incluir informacoes de pagamento (para cupom fiscal)
        if extraction_data and extraction_data.get("payment_info"):
            from app.modules.documents.schemas.document import (
                DetectedPaymentResponse,
                PaymentInfoResponse,
            )

            payment_info = extraction_data["payment_info"]
            payments = []
            for p in payment_info.get("payments", []):
                payments.append(
                    DetectedPaymentResponse(
                        method=p.get("method", ""),
                        amount=p.get("amount", 0),
                        label=p.get("label", ""),
                        sequence=p.get("sequence", 0),
                    )
                )
            response.payment_info = PaymentInfoResponse(
                total=payment_info.get("total"),
                subtotal=payment_info.get("subtotal"),
                discount=payment_info.get("discount"),
                payments=payments,
            )

        return response

    async def upload_batch(self, user: User, files: list) -> Document:
        """Upload de multiplas imagens como 1 documento (para cupons grandes)"""
        from app.modules.documents.schemas.document import (
            CardInfoResponse,
            DocumentResponse,
            ExtractedItemResponse,
        )

        # Validar quantidade de arquivos
        if len(files) < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum arquivo enviado",
            )
        if len(files) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximo de 10 arquivos permitido",
            )

        # Extensoes permitidas para batch (apenas imagens)
        allowed_batch_extensions = {"jpg", "jpeg", "png", "heic", "heif"}

        # Processar cada arquivo
        images: list[tuple[bytes, str]] = []
        total_size = 0
        combined_hash_data = b""

        for file in files:
            ext = file.filename.split(".")[-1].lower() if file.filename else ""
            if ext not in allowed_batch_extensions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Extensao '{ext}' nao permitida. Use: {', '.join(allowed_batch_extensions)}",
                )

            content = await file.read()
            total_size += len(content)

            # Validar tamanho individual (10MB por arquivo)
            if len(content) > settings.max_upload_size_mb * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Arquivo muito grande. Maximo: {settings.max_upload_size_mb}MB por arquivo",
                )

            # Converter HEIC para JPEG se necessario
            if ext in ("heic", "heif"):
                content, mime_type = await self._convert_heic_to_jpeg(content)
            else:
                mime_type = file.content_type or f"image/{ext}"
                # Normalizar mime_type
                if mime_type == "image/jpg":
                    mime_type = "image/jpeg"

            images.append((content, mime_type))
            combined_hash_data += content

        # Validar tamanho total (50MB)
        max_total_size = 50 * 1024 * 1024
        if total_size > max_total_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tamanho total muito grande. Maximo: 50MB",
            )

        # Calcular hash combinado para dedupe
        file_hash = hashlib.sha256(combined_hash_data).hexdigest()

        # Verificar se e duplicata
        existing_result = await self.db.execute(
            select(Document)
            .where(
                Document.user_id == user.id,
                Document.file_hash == file_hash,
            )
            .limit(1)
        )
        existing_document = existing_result.scalar_one_or_none()
        is_duplicate = existing_document is not None

        if is_duplicate:
            print(
                f"[DOC_SVC] Batch duplicate detected (informative only): existing_id={existing_document.id}"
            )

        # Salvar primeira imagem como referencia
        upload_dir = Path(settings.upload_dir) / str(user.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        first_content, first_mime = images[0]
        ext = "jpg" if "jpeg" in first_mime else first_mime.split("/")[-1]
        file_path = upload_dir / f"{file_hash}.{ext}"
        await asyncio.to_thread(_write_file_sync, file_path, first_content)

        # Criar registro do documento
        document = Document(
            user_id=user.id,
            file_path=str(file_path),
            file_hash=file_hash,
            file_size=total_size,
            mime_type=first_mime,
            original_filename=f"batch_{len(files)}_images",
            status=DocumentStatus.PENDING,
        )
        self.db.add(document)
        await self.db.flush()
        await self.db.refresh(document)

        # Processar multiplas imagens usando LLM
        extraction_data = await self._process_batch_images(document, images)

        # Construir resposta
        response = DocumentResponse.model_validate(document)
        response.is_duplicate = is_duplicate

        # Converter itens extraidos para o formato de resposta
        if extraction_data and extraction_data.get("items"):
            from app.modules.known_services.services.recurring_detector import (
                RecurringDetectorService,
            )

            recurring_detector = RecurringDetectorService(self.db)

            card_info = extraction_data.get("card_info", {})
            invoice_month = card_info.get("invoice_month") if card_info else None
            invoice_year = card_info.get("invoice_year") if card_info else None

            items_with_detection = await recurring_detector.detect_all(
                user=user,
                items=extraction_data["items"],
                invoice_month=invoice_month,
                invoice_year=invoice_year,
            )

            # Filtrar itens com valor != 0
            valid_items = [item for item in items_with_detection if item.get("amount", 0) != 0]

            # Verificar duplicatas em batch (1 query)
            items_for_dup_check = [
                (item.get("description", "Item"), item.get("amount", 0), item.get("date"))
                for item in valid_items
            ]
            duplicate_results = await self._check_duplicates_batch(user, items_for_dup_check)

            extracted_items = []
            for idx, item in enumerate(valid_items):
                duplicate_info = (
                    duplicate_results[idx]
                    if idx < len(duplicate_results)
                    else {"is_duplicate": False, "transaction_id": None}
                )

                future_installments = None
                if item.get("future_installments"):
                    from app.modules.documents.schemas.document import FutureInstallmentResponse

                    future_installments = [
                        FutureInstallmentResponse(
                            installment=fi.get("installment"),
                            reference_month=fi.get("reference_month"),
                            reference_year=fi.get("reference_year"),
                        )
                        for fi in item["future_installments"]
                        if fi.get("installment")
                        and fi.get("reference_month")
                        and fi.get("reference_year")
                    ]

                recurring_detection = None
                if item.get("recurring_detection"):
                    from app.modules.known_services.schemas.recurring_detection import (
                        RecurringDetection,
                    )

                    recurring_detection = RecurringDetection(**item["recurring_detection"])

                extracted_items.append(
                    ExtractedItemResponse(
                        description=item.get("description", "Item"),
                        amount=item.get("amount", 0),
                        date=item.get("date"),
                        category=item.get("category"),
                        confidence=item.get("confidence", 0.9),
                        transaction_type=item.get("transaction_type"),
                        is_installment=item.get("is_installment", False),
                        installment_current=item.get("installment_current"),
                        installment_total=item.get("installment_total"),
                        future_installments=future_installments if future_installments else None,
                        is_duplicate=duplicate_info["is_duplicate"],
                        existing_transaction_id=duplicate_info.get("transaction_id"),
                        recurring_detection=recurring_detection,
                        quantity=item.get("quantity"),
                        unit=item.get("unit"),
                        unit_price=item.get("unit_price"),
                        grocery_category=item.get("grocery_category"),
                        necessity_type=item.get("necessity_type"),
                    )
                )

            response.extracted_items = extracted_items

        if extraction_data and extraction_data.get("card_info"):
            card_info = extraction_data["card_info"]
            response.card_info = CardInfoResponse(
                card_issuer=card_info.get("card_issuer"),
                card_bank=card_info.get("card_bank"),
                card_brand=card_info.get("card_brand"),
                card_partner=card_info.get("card_partner"),
                card_last_digits=card_info.get("card_last_digits"),
                card_name=card_info.get("card_name"),
                invoice_month=card_info.get("invoice_month"),
                invoice_year=card_info.get("invoice_year"),
                closing_date=card_info.get("closing_date"),
                closing_day=card_info.get("closing_day"),
                due_date=card_info.get("due_date"),
                due_day=card_info.get("due_day"),
                total_amount=card_info.get("total_amount"),
                credit_limit=card_info.get("credit_limit"),
                credit_used=card_info.get("credit_used"),
                credit_available=card_info.get("credit_available"),
            )

        # Incluir informacoes de pagamento (para cupom fiscal)
        if extraction_data and extraction_data.get("payment_info"):
            from app.modules.documents.schemas.document import (
                DetectedPaymentResponse,
                PaymentInfoResponse,
            )

            payment_info = extraction_data["payment_info"]
            payments = []
            for p in payment_info.get("payments", []):
                payments.append(
                    DetectedPaymentResponse(
                        method=p.get("method", ""),
                        amount=p.get("amount", 0),
                        label=p.get("label", ""),
                        sequence=p.get("sequence", 0),
                    )
                )
            response.payment_info = PaymentInfoResponse(
                total=payment_info.get("total"),
                subtotal=payment_info.get("subtotal"),
                discount=payment_info.get("discount"),
                payments=payments,
            )

        return response

    async def _convert_heic_to_jpeg(self, heic_content: bytes) -> tuple[bytes, str]:
        """Converte imagem HEIC para JPEG usando pillow-heif"""
        import io

        def _convert():
            try:
                import pillow_heif
                from PIL import Image

                # Registrar o plugin HEIF
                pillow_heif.register_heif_opener()

                # Abrir imagem HEIC
                img = Image.open(io.BytesIO(heic_content))

                # Converter para RGB se necessario (HEIC pode ter alpha)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Salvar como JPEG
                output = io.BytesIO()
                img.save(output, format="JPEG", quality=85)
                return output.getvalue()
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="pillow-heif nao instalado. Execute: pip install pillow-heif",
                )
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Erro ao converter HEIC: {str(e)}",
                )

        jpeg_content = await asyncio.to_thread(_convert)
        return jpeg_content, "image/jpeg"

    async def _process_batch_images(
        self, document: Document, images: list[tuple[bytes, str]]
    ) -> dict | None:
        """Processa multiplas imagens e extrai dados usando LLM"""
        try:
            print(f"[DOC_SVC] _process_batch_images: id={document.id}, num_images={len(images)}")
            document.status = DocumentStatus.PROCESSING
            await self.db.flush()

            # Usar LLM com visao para processar multiplas imagens
            # Mistral como provider principal (melhor OCR)
            from app.modules.documents.services.llm_ocr_service import LLMOCRService

            if settings.mistral_api_key:
                llm_service = LLMOCRService(provider="mistral", model=settings.mistral_llm_model)
                print("[DOC_SVC] Using Mistral for batch image extraction")
            else:
                llm_service = LLMOCRService(
                    provider="google", model=settings.vision_model or "gemini-2.0-flash"
                )
                print("[DOC_SVC] Using Google for batch image extraction (Mistral not configured)")
            result = await llm_service.extract_from_multiple_images(images)

            items_count = len(result.get("items", [])) if result else 0
            print(
                f"[DOC_SVC] Batch extraction returned: items={items_count}, error={result.get('error')}"
            )

            if result is None or (not result.get("items") and result.get("error")):
                document.status = DocumentStatus.FAILED
                document.error_message = result.get("error") if result else "Extracao falhou"
                print(
                    f"[DOC_SVC] Document {document.id} marked as FAILED: {document.error_message}"
                )
            else:
                document.status = DocumentStatus.COMPLETED
                print(
                    f"[DOC_SVC] Document {document.id} marked as COMPLETED with {items_count} items"
                )

            # Determinar tipo de documento
            doc_type = result.get("document_type")
            if doc_type:
                document.document_type = doc_type

            document.processed_at = utc_now()
            await self.db.flush()
            await self.db.refresh(document)

            return result

        except Exception as e:
            print(f"[DOC_SVC] EXCEPTION in _process_batch_images: {e}")
            import traceback

            traceback.print_exc()
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            await self.db.flush()
            await self.db.refresh(document)
            return None

    async def get_by_id(self, user: User, document_id: int) -> Document | None:
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user.id,
            )
        )
        return result.scalar_one_or_none()

    async def list(self, user: User, limit: int = 50, offset: int = 0) -> list[Document]:
        result = await self.db.execute(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def retry_processing(self, user: User, document_id: int) -> Document:
        document = await self.get_by_id(user, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento nao encontrado",
            )

        if document.status == DocumentStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Documento ja esta sendo processado",
            )

        # Ler arquivo em thread separada para nao bloquear o event loop
        content = await asyncio.to_thread(_read_file_sync, document.file_path)

        document.status = DocumentStatus.PENDING
        await self._process_document(document, content)
        return document

    async def delete(self, user: User, document_id: int) -> None:
        document = await self.get_by_id(user, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento nao encontrado",
            )

        # Apagar arquivo
        if os.path.exists(document.file_path):
            os.remove(document.file_path)

        await self.db.delete(document)

    async def _process_document(
        self, document: Document, content: bytes, password: str | None = None
    ) -> dict | None:
        """Processa documento e extrai dados (NAO salva - retorna para confirmacao)

        Args:
            document: Document model instance
            content: File content as bytes
            password: Optional password for protected PDFs
        """
        try:
            print(
                f"[DOC_SVC] _process_document: id={document.id}, mime_type={document.mime_type}, content_size={len(content)}"
            )
            document.status = DocumentStatus.PROCESSING
            await self.db.flush()

            # Extrair dados com LLM
            print("[DOC_SVC] Calling _extract_data...")
            extraction_data = await self._extract_data(document, content, password)
            items_count = len(extraction_data.get("items", [])) if extraction_data else 0
            print(
                f"[DOC_SVC] _extract_data returned: items={items_count}, error={document.error_message}"
            )

            # Se houve erro na extracao, marcar como falha
            if extraction_data is None or (
                not extraction_data.get("items") and document.error_message
            ):
                document.status = DocumentStatus.FAILED
                print(
                    f"[DOC_SVC] Document {document.id} marked as FAILED: {document.error_message}"
                )
            else:
                document.status = DocumentStatus.COMPLETED
                print(
                    f"[DOC_SVC] Document {document.id} marked as COMPLETED with {items_count} items"
                )

            document.processed_at = utc_now()
            await self.db.flush()
            await self.db.refresh(document)

            return extraction_data

        except Exception as e:
            print(f"[DOC_SVC] EXCEPTION in _process_document: {e}")
            import traceback

            traceback.print_exc()
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            await self.db.flush()
            await self.db.refresh(document)
            return None

    async def _extract_data(
        self, document: Document, content: bytes, password: str | None = None
    ) -> dict | None:
        """Extrai dados do documento usando LLM com visao ou parser de planilha

        Args:
            document: Document model instance
            content: File content as bytes
            password: Optional password for protected PDFs
        """
        print(f"[DOC_SVC] _extract_data: content_size={len(content)}")

        # Verificar se e CSV ou Excel
        mime_type = document.mime_type or ""
        filename = document.original_filename or ""

        is_spreadsheet = mime_type in [
            "text/csv",
            "application/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ] or filename.lower().endswith((".csv", ".xlsx", ".xls"))

        print(
            f"[DOC_SVC] mime_type={mime_type}, filename={filename}, is_spreadsheet={is_spreadsheet}"
        )

        if is_spreadsheet:
            # Usar parser de planilha
            from app.modules.documents.services.spreadsheet_parser_service import (
                SpreadsheetParserService,
            )

            parser = SpreadsheetParserService()
            result = await parser.parse_file(content, filename, mime_type)
        else:
            # Usar LLM com visao para imagens/PDFs
            # Respeitar vision_provider configurado (default: google)
            selected_provider = settings.vision_provider
            if selected_provider == "mistral" and settings.mistral_api_key:
                selected_model = settings.mistral_llm_model
            elif selected_provider == "google" and settings.google_api_key:
                selected_model = settings.vision_model or "gemini-2.0-flash"
            elif settings.google_api_key:
                selected_provider = "google"
                selected_model = settings.vision_model or "gemini-2.0-flash"
            elif settings.mistral_api_key:
                selected_provider = "mistral"
                selected_model = settings.mistral_llm_model
            else:
                selected_provider = "google"
                selected_model = "gemini-2.0-flash"
            print(f"[DOC_SVC] Using {selected_provider} for extraction")

            from app.modules.documents.services.llm_ocr_service import LLMOCRService

            llm_service = LLMOCRService(provider=selected_provider, model=selected_model)
            result = await llm_service.extract_from_image(
                content, mime_type, filename=filename, password=password
            )
            print(
                f"[DOC_SVC] LLM OCR result: items={len(result.get('items', []))}, error={result.get('error')}"
            )

        # Se houve erro na extracao
        if result.get("error"):
            document.error_message = result["error"]
            return None

        # Determinar tipo de documento
        doc_type = result.get("document_type")
        if doc_type:
            document.document_type = doc_type

        # Retornar itens individuais com categoria, info do cartao e info de pagamento
        items = result.get("items", [])
        card_info = result.get("card_info")
        payment_info = result.get("payment_info")

        return {
            "items": items,
            "document_type": doc_type,
            "card_info": card_info,
            "payment_info": payment_info,
        }

    async def _check_duplicate_transaction(
        self,
        user: User,
        description: str,
        amount: float,
        item_date: str | None,
    ) -> dict:
        """
        Verifica se ja existe uma transacao similar no banco.
        Usa a versao batch internamente para manter consistencia.
        """
        results = await self._check_duplicates_batch(user, [(description, amount, item_date)])
        return results[0] if results else {"is_duplicate": False, "transaction_id": None}

    async def _check_duplicates_batch(
        self,
        user: User,
        items: list[tuple[str, float, str | None]],  # [(description, amount, date), ...]
    ) -> list[dict]:
        """
        Verifica duplicatas em batch (1 query para todos os itens).

        Uma transacao e considerada duplicada se:
        - Mesmo usuario
        - Mesmo valor (absoluto, com tolerancia de R$ 0.01)
        - Descricao similar (contem partes em comum)
        - Mesma data (se fornecida)

        Returns:
            Lista de dicts com is_duplicate (bool) e transaction_id (int | None)
        """
        if not items:
            return []

        try:
            from sqlalchemy import or_

            # Coletar todos os valores unicos para busca
            amounts_set = set()
            dates_set = set()
            tolerance = Decimal("0.01")

            for description, amount, item_date in items:
                amount_decimal = Decimal(str(abs(amount)))
                amounts_set.add(amount_decimal)
                if item_date:
                    try:
                        dates_set.add(date.fromisoformat(item_date))
                    except ValueError:
                        pass

            # Construir condições para buscar todos os candidatos em uma query
            amount_conditions = []
            for amt in amounts_set:
                amount_conditions.append(func.abs(Transaction.amount - amt) <= tolerance)

            query = select(Transaction).where(
                Transaction.user_id == user.id,
                or_(*amount_conditions) if amount_conditions else True,
            )

            # Filtrar por datas se houver
            if dates_set:
                query = query.where(
                    or_(Transaction.date.in_(dates_set), Transaction.date.is_(None))
                )

            result = await self.db.execute(query.limit(100))
            all_candidates = list(result.scalars().all())

            # Agora verificar cada item contra os candidatos carregados
            results = []
            for description, amount, item_date in items:
                target_date = None
                if item_date:
                    try:
                        target_date = date.fromisoformat(item_date)
                    except ValueError:
                        pass

                amount_decimal = Decimal(str(abs(amount)))

                # Filtrar candidatos por valor e data
                candidates = [
                    txn
                    for txn in all_candidates
                    if abs(txn.amount - amount_decimal) <= tolerance
                    and (target_date is None or txn.date == target_date)
                ]

                if not candidates:
                    results.append({"is_duplicate": False, "transaction_id": None})
                    continue

                # Verificar similaridade de descricao
                description_lower = description.lower().strip()
                description_words = set(description_lower.split())
                found_duplicate = False
                duplicate_id = None

                for txn in candidates:
                    txn_desc = (txn.description or "").lower().strip()
                    txn_words = set(txn_desc.split())

                    # Considerar duplicado se:
                    # 1. Descricoes sao iguais
                    # 2. Uma contem a outra
                    # 3. Tem palavras significativas em comum (>= 50% das palavras)
                    if description_lower == txn_desc:
                        found_duplicate = True
                        duplicate_id = txn.id
                        break

                    if description_lower in txn_desc or txn_desc in description_lower:
                        found_duplicate = True
                        duplicate_id = txn.id
                        break

                    # Verificar palavras em comum (ignorar palavras curtas)
                    significant_words = {w for w in description_words if len(w) > 3}
                    txn_significant = {w for w in txn_words if len(w) > 3}

                    if significant_words and txn_significant:
                        common = significant_words & txn_significant
                        similarity = len(common) / max(len(significant_words), len(txn_significant))
                        if similarity >= 0.5:
                            found_duplicate = True
                            duplicate_id = txn.id
                            break

                results.append({"is_duplicate": found_duplicate, "transaction_id": duplicate_id})

            return results

        except Exception as e:
            print(f"[DOC_SVC] Error in batch duplicate check: {e}")
            # Em caso de erro, retornar todos como nao duplicados
            return [{"is_duplicate": False, "transaction_id": None} for _ in items]

    async def save_card_password(self, user: User, card_id: int, password: str):
        """Encrypt and save invoice password to credit card

        Args:
            user: Current user
            card_id: Credit card ID
            password: Plain text password to encrypt and save

        Raises:
            HTTPException: If card not found or doesn't belong to user
        """
        from app.core.crypto import encrypt_password

        result = await self.db.execute(
            select(CreditCard).where(CreditCard.id == card_id, CreditCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()

        if not card:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cartão não encontrado"
            )

        card.invoice_password_encrypted = encrypt_password(password)
        await self.db.commit()
        print(f"[DOC_SVC] Saved encrypted password for credit card {card_id}")
