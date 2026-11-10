from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_usage import AIUnavailable, metered, reserve_document, usage_context
from app.core.config import settings
from app.core.database import async_session_maker
from app.core.utils import utc_now
from app.models.credit_card import CreditCard
from app.models.document import Document, DocumentStage, DocumentStatus
from app.models.transaction import Transaction
from app.models.user import User
from app.modules.documents.services.ai_failures import (
    AI_QUOTA_EXHAUSTED,
    FILE_MISSING,
    MAX_AI_ATTEMPTS,
    PASSWORD_REQUIRED,
    PROCESSING_TIMEOUT,
    Failure,
    ai_circuit,
    classify,
    next_retry_at,
)
from app.modules.documents.services.upload_files import prepare_upload

logger = logging.getLogger(__name__)


class PasswordRequiredError(Exception):
    """Special error for inline password request - not a failure"""


def _write_file_sync(file_path: Path, content: bytes) -> None:
    """Escrita sincrona de arquivo - para uso com asyncio.to_thread"""
    with open(file_path, "wb") as f:
        f.write(content)


def _read_file_sync(file_path: str) -> bytes:
    """Leitura sincrona de arquivo - para uso com asyncio.to_thread"""
    with open(file_path, "rb") as f:
        return f.read()


# Teto da extração inteira (retries e modelo alternativo inclusos); cada chamada ao
# Gemini tem o próprio timeout no GoogleProvider. Acima disso vira ai_busy e volta à fila.
EXTRACTION_TIMEOUT_SECONDS = 300
# processing mais antigo que isso = processo reiniciado no meio (#37)
STALE_PROCESSING = timedelta(minutes=15)
MAX_STALE_ATTEMPTS = 3


def mark_processing(document: Document) -> None:
    document.status = DocumentStatus.PROCESSING
    document.stage = DocumentStage.EXTRACTING
    document.processing_started_at = utc_now()
    document.next_retry_at = None


def mark_completed(document: Document) -> None:
    document.status = DocumentStatus.COMPLETED
    document.stage = DocumentStage.DONE
    document.error_code = None
    document.error_message = None
    document.next_retry_at = None
    document.processing_started_at = None
    ai_circuit.record_success()


def mark_failure(
    document: Document, error: BaseException | str | Failure | None, retry: bool = True
) -> Failure:
    """RN016: falha da IA vira waiting_ai com nova tentativa; o resto, failed.
    error_message recebe só o texto do catálogo; o erro cru nunca sai da API.
    retry=False quando não há como reprocessar sozinho (lote de imagens)."""
    failure = error if isinstance(error, Failure) else classify(error)
    document.error_code = failure.code
    document.error_message = failure.message
    document.processing_started_at = None
    document.next_retry_at = None

    if failure.retry_after is None or not retry:
        document.status = DocumentStatus.FAILED
        document.stage = DocumentStage.FAILED
    else:
        document.attempts = (document.attempts or 0) + 1
        if document.attempts >= MAX_AI_ATTEMPTS:
            document.status = DocumentStatus.FAILED
            document.stage = DocumentStage.FAILED
        else:
            document.status = DocumentStatus.WAITING_AI
            document.stage = DocumentStage.WAITING
            document.next_retry_at = next_retry_at(failure, document.attempts)
            ai_circuit.record(failure, document.next_retry_at)

    logger.warning(
        "document_failure document_id=%s code=%s status=%s attempts=%s",
        document.id,
        failure.code,
        document.status,
        document.attempts,
    )
    return failure


async def notify_document_result(db: AsyncSession, document: Document) -> None:
    """#43: o upload assíncrono termina com o app fechado; a notificação vira push.
    waiting_ai não avisa: a leitura ainda vai acontecer."""
    from app.models.notification import NotificationPriority, NotificationType
    from app.modules.notifications.services.notification_service import NotificationService

    if document.status == DocumentStatus.COMPLETED:
        count = len((document.extracted_data or {}).get("items") or [])
        kind = NotificationType.DOCUMENT_PROCESSED
        title = "Fatura lida"
        message = f"{count} {'compra pronta' if count == 1 else 'compras prontas'} para conferir."
        priority = NotificationPriority.NORMAL
    elif document.status == DocumentStatus.FAILED:
        kind = NotificationType.DOCUMENT_FAILED
        title = "Não conseguimos ler o arquivo"
        message = document.error_message or "Tente enviar de novo."
        priority = NotificationPriority.HIGH
    else:
        return
    await NotificationService(db).send_notification(
        user_id=document.user_id,
        notification_type=kind,
        title=title,
        message=message,
        entity_type="document",
        entity_id=document.id,
        action_url=f"/documents/{document.id}",
        action_label="Conferir",
        priority=priority,
        icon="file-text",
    )


def wait_for_ai(document: Document) -> None:
    """Disjuntor aberto: guarda o documento sem chamar a IA"""
    document.status = DocumentStatus.WAITING_AI
    document.stage = DocumentStage.WAITING
    document.error_code = AI_QUOTA_EXHAUSTED.code
    document.error_message = AI_QUOTA_EXHAUSTED.message
    document.next_retry_at = ai_circuit.paused_until
    document.processing_started_at = None


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

    logger.info("[DOC_BG] Iniciando processamento background: document_id=%s", document_id)

    file_bytes = None
    try:
        # Ler arquivo do disco (em thread para nao bloquear)
        file_bytes = await asyncio.to_thread(_read_file_sync, file_path)
    except Exception as e:
        logger.error(
            "document_processing_failed document_id=%s error_type=%s", document_id, type(e).__name__
        )
        async with async_session_maker() as db:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document:
                mark_failure(document, FILE_MISSING)
                await db.commit()
        return

    async with async_session_maker() as db:
        try:
            # Buscar documento
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()

            if not document:
                logger.info("[DOC_BG] Documento %s nao encontrado", document_id)
                return

            # Buscar usuario
            from app.models.user import User

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                document.status = DocumentStatus.FAILED
                document.stage = DocumentStage.FAILED
                document.error_message = "Usuario nao encontrado"
                await db.commit()
                return

            if ai_circuit.is_open():
                wait_for_ai(document)
                await db.commit()
                return

            # Processar documento
            mark_processing(document)
            await db.commit()

            from app.modules.documents.services.llm_ocr_service import LLMOCRService

            selected_provider = settings.vision_provider
            selected_model = settings.vision_model
            if selected_provider == "deepseek" and settings.deepseek_api_key:
                selected_model = settings.vision_model
            elif selected_provider == "mistral" and settings.mistral_api_key:
                selected_model = settings.mistral_llm_model
            elif selected_provider == "google" and settings.google_api_key:
                selected_model = settings.vision_model
            elif settings.deepseek_api_key:
                selected_provider = "deepseek"
                selected_model = settings.vision_model
            elif settings.mistral_api_key:
                selected_provider = "mistral"
                selected_model = settings.mistral_llm_model
            elif settings.google_api_key:
                selected_provider = "google"
                selected_model = settings.vision_model

            logger.info("[DOC_BG] Using provider=%s model=%s for extraction", selected_provider, selected_model)
            llm_service = LLMOCRService(provider=selected_provider, model=selected_model)

            with usage_context(db, user_id, document_id):
                extraction_data = await asyncio.wait_for(
                    llm_service.extract_from_image(
                        file_bytes, mime_type, filename=filename, password=password
                    ),
                    timeout=EXTRACTION_TIMEOUT_SECONDS,
                )

            # Verificar se houve erro
            if extraction_data is None or extraction_data.get("error"):
                mark_failure(document, extraction_data.get("error") if extraction_data else None)
            else:
                # o app acompanha pelo GET /documents/{id}: grava a etapa antes de conferir
                document.stage = DocumentStage.VALIDATING
                await db.commit()
                # Validar se a soma dos itens bate com o total da fatura
                if extraction_data.get("document_type") == "fatura_cartao":
                    total_amount = extraction_data.get("card_info", {}).get("total_amount")
                    items = extraction_data.get("items", [])

                    if total_amount and items:
                        items_sum = sum(item.get("amount", 0) for item in items)
                        difference = abs(total_amount - items_sum)

                        # Se diferença > R$ 50, há itens faltando ou sobrando
                        if difference > 50:
                            # Adicionar flag nos extracted_data para o frontend alertar o usuário
                            extraction_data["validation_warning"] = {
                                "type": "sum_mismatch",
                                "expected": total_amount,
                                "actual": items_sum,
                                "difference": difference,
                                "message": f"A soma das transações (R$ {items_sum:.2f}) não bate com o total da fatura (R$ {total_amount:.2f}). Diferença: R$ {difference:.2f}",
                            }

                mark_completed(document)
                document.document_type = extraction_data.get("document_type")
                # Salvar dados extraidos para recuperacao posterior
                document.extracted_data = extraction_data
                logger.info(
                    "document_processing_completed document_id=%s item_count=%s",
                    document_id,
                    len(extraction_data.get("items", [])),
                )

            document.processed_at = utc_now()
            await notify_document_result(db, document)
            await db.commit()

        except Exception as e:
            logger.error(
                "document_processing_failed document_id=%s error_type=%s",
                document_id,
                type(e).__name__,
            )

            try:
                result = await db.execute(select(Document).where(Document.id == document_id))
                document = result.scalar_one_or_none()
                if document:
                    mark_failure(document, e)
                    await db.commit()
            except Exception:
                pass

        finally:
            # Cleanup explicito para liberar memoria
            del file_bytes
            gc.collect()


async def retry_waiting_documents(limit: int = 5) -> int:
    """Job do scheduler (RN016/#37): solta processing preso e reprocessa waiting_ai vencido.

    Devolve quantos documentos foram reprocessados. Para no primeiro sinal de cota
    esgotada (disjuntor aberto) para não martelar a IA.
    """
    now = utc_now()
    async with async_session_maker() as db:
        # processing antigo = API reiniciou no meio; created_at cobre linhas de antes da #37
        stale = (
            await db.execute(
                select(Document).where(
                    Document.status == DocumentStatus.PROCESSING,
                    func.coalesce(Document.processing_started_at, Document.created_at)
                    < now - STALE_PROCESSING,
                )
            )
        ).scalars()
        for document in stale:
            document.attempts = (document.attempts or 0) + 1
            if document.attempts >= MAX_STALE_ATTEMPTS:
                mark_failure(document, PROCESSING_TIMEOUT)
            else:
                document.status = DocumentStatus.WAITING_AI
                document.stage = DocumentStage.WAITING
                document.next_retry_at = now
                document.processing_started_at = None
            logger.warning(
                "document_stale_processing document_id=%s attempts=%s",
                document.id,
                document.attempts,
            )
        await db.commit()

        if ai_circuit.is_open(now):
            return 0
        due = (
            await db.execute(
                select(
                    Document.id,
                    Document.user_id,
                    Document.file_path,
                    Document.mime_type,
                    Document.original_filename,
                )
                .where(
                    Document.status == DocumentStatus.WAITING_AI,
                    Document.next_retry_at <= now,
                )
                .order_by(Document.next_retry_at)
                .limit(limit)
            )
        ).all()

    processed = 0
    for doc_id, user_id, file_path, mime_type, filename in due:
        if ai_circuit.is_open():
            break
        problem = await _unprocessable_without_user(file_path, mime_type)
        if problem is not None:
            async with async_session_maker() as db:
                document = await db.get(Document, doc_id)
                if document:
                    mark_failure(document, problem)
                    await db.commit()
            continue
        await process_document_background(doc_id, user_id, file_path, mime_type, filename)
        processed += 1
    return processed


async def _unprocessable_without_user(file_path: str, mime_type: str) -> Failure | None:
    """O job não tem a senha do PDF nem como recuperar arquivo apagado"""
    if not os.path.exists(file_path):
        return FILE_MISSING
    if mime_type == "application/pdf":
        from app.modules.documents.services.pdf_converter import check_pdf_needs_password

        content = await asyncio.to_thread(_read_file_sync, file_path)
        if check_pdf_needs_password(content):
            return PASSWORD_REQUIRED
    return None


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _find_by_hash(self, user: User, file_hash: str) -> Document | None:
        result = await self.db.execute(
            select(Document).where(
                Document.user_id == user.id,
                Document.file_hash == file_hash,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _duplicate_error(existing: Document) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "duplicate",
                "message": "Este documento ja foi enviado",
                "document_id": existing.id,
            },
        )

    async def _resolve_duplicate(self, user: User, file_hash: str, force: bool) -> Document | None:
        """Bloqueia reenvio (409) ou, com force=True, devolve o documento existente para reprocessar."""
        existing = await self._find_by_hash(user, file_hash)
        if existing is None:
            return None
        if not force:
            raise self._duplicate_error(existing)
        if existing.status == DocumentStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Documento já está sendo processado",
            )
        existing.error_message = None
        return existing

    async def _add_document(self, user: User, document: Document) -> None:
        """Persiste o documento; upload concorrente do mesmo arquivo vira 409."""
        self.db.add(document)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            existing = await self._find_by_hash(user, document.file_hash)
            if existing is None:
                raise
            raise self._duplicate_error(existing)
        await self.db.refresh(document)

    async def upload_async(
        self,
        user: User,
        file: UploadFile,
        background_tasks: BackgroundTasks,
        password: str | None = None,
        credit_card_id: int | None = None,
        force: bool = False,
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
            force: Reprocessa o documento existente em vez de devolver 409
        """
        from app.modules.documents.schemas.document import DocumentAsyncUploadResponse

        prepared = await prepare_upload(file)
        content = prepared.content

        # Check if PDF requires password
        if prepared.mime_type == "application/pdf":
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
                        except Exception as e:
                            logger.error("upload_async_failed error_type=%s", type(e).__name__)

                # If still no password, raise special error
                if password is None:
                    raise PasswordRequiredError("PDF protegido por senha")

        # Calcular hash para dedupe
        file_hash = hashlib.sha256(content).hexdigest()
        existing_document = await self._resolve_duplicate(user, file_hash, force)
        await reserve_document(self.db, user)

        # Salvar arquivo
        upload_dir = Path(settings.upload_dir) / str(user.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / f"{file_hash}.{prepared.extension}"
        await asyncio.to_thread(_write_file_sync, file_path, content)

        # Guardar tamanho antes de limpar content
        content_size = len(content)

        if existing_document is not None:
            document = existing_document
            document.file_path = str(file_path)
            document.mime_type = prepared.mime_type
            document.file_size = content_size
            document.status = DocumentStatus.PROCESSING
            document.stage = DocumentStage.RECEIVED
            await self.db.flush()
        else:
            # Criar registro com status PROCESSING
            document = Document(
                user_id=user.id,
                file_path=str(file_path),
                file_hash=file_hash,
                file_size=content_size,
                mime_type=prepared.mime_type,
                original_filename=prepared.original_filename,
                status=DocumentStatus.PROCESSING,  # Ja marca como processing
            )
            await self._add_document(user, document)
        # Gravar antes de agendar: a tarefa abre outra sessão e pode começar antes do
        # commit automático do fim da requisição (FastAPI >= 0.120)
        await self.db.commit()

        # Limpar content da memoria - arquivo ja esta no disco
        del content

        # Agendar processamento em background (passa file_path ao inves de bytes)
        background_tasks.add_task(
            process_document_background,
            document.id,
            user.id,
            str(file_path),  # Passa path ao inves de bytes para economizar memoria
            prepared.mime_type,
            prepared.original_filename,
            password,  # Pass password to background task
        )

        logger.info("[DOC_SVC] Upload async agendado: document_id=%s", document.id)

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
        force: bool = False,
    ) -> Document:
        prepared = await prepare_upload(file)
        content = prepared.content

        # Check if PDF requires password
        if prepared.mime_type == "application/pdf":
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
                        except Exception as e:
                            logger.error("upload_failed error_type=%s", type(e).__name__)
                            # Password might be invalid, will raise PasswordRequiredError below

                # If still no password, raise special error
                if password is None:
                    raise PasswordRequiredError("PDF protegido por senha")

        # Calcular hash para dedupe
        file_hash = hashlib.sha256(content).hexdigest()
        existing_document = await self._resolve_duplicate(user, file_hash, force)
        await reserve_document(self.db, user)
        is_duplicate = existing_document is not None

        # Salvar arquivo
        upload_dir = Path(settings.upload_dir) / str(user.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = upload_dir / f"{file_hash}.{prepared.extension}"
        # Escrita em thread separada para nao bloquear o event loop
        await asyncio.to_thread(_write_file_sync, file_path, content)

        if existing_document is not None:
            document = existing_document
            document.file_path = str(file_path)
            document.mime_type = prepared.mime_type
            document.file_size = len(content)
            document.status = DocumentStatus.PENDING
            document.stage = DocumentStage.RECEIVED
        else:
            document = Document(
                user_id=user.id,
                file_path=str(file_path),
                file_hash=file_hash,
                file_size=len(content),
                mime_type=prepared.mime_type,
                original_filename=prepared.original_filename,
                status=DocumentStatus.PENDING,
            )
            await self._add_document(user, document)

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

    async def upload_batch(self, user: User, files: list, force: bool = False) -> Document:
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
                detail="Máximo de 10 arquivos permitido",
            )

        images: list[tuple[bytes, str]] = []
        total_size = 0
        combined_hash_data = b""

        for file in files:
            prepared = await prepare_upload(file, images_only=True)
            total_size += prepared.original_size
            images.append((prepared.content, prepared.mime_type))
            combined_hash_data += prepared.content

        max_total_size = 50 * 1024 * 1024
        if total_size > max_total_size:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Tamanho total muito grande. Máximo: 50MB",
            )

        # Calcular hash combinado para dedupe
        file_hash = hashlib.sha256(combined_hash_data).hexdigest()
        existing_document = await self._resolve_duplicate(user, file_hash, force)
        await reserve_document(self.db, user)
        is_duplicate = existing_document is not None

        # Salvar primeira imagem como referencia
        upload_dir = Path(settings.upload_dir) / str(user.id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        first_content, first_mime = images[0]
        ext = "jpg" if "jpeg" in first_mime else first_mime.split("/")[-1]
        file_path = upload_dir / f"{file_hash}.{ext}"
        await asyncio.to_thread(_write_file_sync, file_path, first_content)

        if existing_document is not None:
            document = existing_document
            document.file_path = str(file_path)
            document.status = DocumentStatus.PENDING
            document.stage = DocumentStage.RECEIVED
        else:
            document = Document(
                user_id=user.id,
                file_path=str(file_path),
                file_hash=file_hash,
                file_size=total_size,
                mime_type=first_mime,
                original_filename=f"batch_{len(files)}_images",
                status=DocumentStatus.PENDING,
            )
            await self._add_document(user, document)

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

    @metered("extraction", document_arg="document")
    async def _process_batch_images(
        self, document: Document, images: list[tuple[bytes, str]]
    ) -> dict | None:
        """Processa multiplas imagens e extrai dados usando LLM"""
        try:
            logger.info(
                "[DOC_SVC] _process_batch_images: id=%s, num_images=%s", document.id, len(images)
            )
            mark_processing(document)
            await self.db.flush()

            # Usar LLM com visao para processar multiplas imagens
            # Mistral como provider principal (melhor OCR)
            from app.modules.documents.services.llm_ocr_service import LLMOCRService

            selected_provider = settings.vision_provider
            selected_model = settings.vision_model
            if selected_provider == "deepseek" and settings.deepseek_api_key:
                selected_model = settings.vision_model
            elif selected_provider == "mistral" and settings.mistral_api_key:
                selected_model = settings.mistral_llm_model
            elif selected_provider == "google" and settings.google_api_key:
                selected_model = settings.vision_model
            elif settings.deepseek_api_key:
                selected_provider = "deepseek"
                selected_model = settings.vision_model
            elif settings.mistral_api_key:
                selected_provider = "mistral"
                selected_model = settings.mistral_llm_model
            elif settings.google_api_key:
                selected_provider = "google"
                selected_model = settings.vision_model

            logger.info("[DOC_SVC] Using %s (%s) for batch image extraction", selected_provider, selected_model)
            llm_service = LLMOCRService(provider=selected_provider, model=selected_model)
            result = await llm_service.extract_from_multiple_images(images)

            items_count = len(result.get("items", [])) if result else 0

            if result is None or (not result.get("items") and result.get("error")):
                # várias imagens num documento só: o job não tem como reprocessar
                mark_failure(document, result.get("error") if result else None, retry=False)
            else:
                mark_completed(document)
                logger.info(
                    "document_processing_completed document_id=%s item_count=%s",
                    document.id,
                    items_count,
                )

            # Determinar tipo de documento
            doc_type = result.get("document_type")
            if doc_type:
                document.document_type = doc_type

            document.processed_at = utc_now()
            await self.db.flush()
            await self.db.refresh(document)

            return result

        except AIUnavailable:
            raise

        except Exception as e:
            logger.error(
                "document_processing_failed document_id=%s error_type=%s",
                document.id,
                type(e).__name__,
            )

            mark_failure(document, e, retry=False)
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
                detail="Documento não encontrado",
            )

        if document.status == DocumentStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Documento já está sendo processado",
            )

        if not os.path.exists(document.file_path):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail={
                    "error": "file_missing",
                    "message": "O arquivo deste documento nao esta mais disponivel. "
                    "Exclua o documento e envie o arquivo novamente.",
                },
            )

        await reserve_document(self.db, user)

        # Ler arquivo em thread separada para nao bloquear o event loop
        content = await asyncio.to_thread(_read_file_sync, document.file_path)

        document.status = DocumentStatus.PENDING
        document.stage = DocumentStage.RECEIVED
        await self._process_document(document, content)
        return document

    async def delete(self, user: User, document_id: int) -> None:
        document = await self.get_by_id(user, document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documento não encontrado",
            )

        # Documentos antigos (anteriores ao indice unico) podem compartilhar o mesmo arquivo
        shared_with = await self.db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.file_path == document.file_path, Document.id != document.id)
        )
        if not shared_with and os.path.exists(document.file_path):
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
            if ai_circuit.is_open():
                wait_for_ai(document)
                await self.db.flush()
                await self.db.refresh(document)
                return None

            mark_processing(document)
            document.error_message = None
            await self.db.flush()

            # Extrair dados com LLM
            extraction_data = await asyncio.wait_for(
                self._extract_data(document, content, password),
                timeout=EXTRACTION_TIMEOUT_SECONDS,
            )
            items_count = len(extraction_data.get("items", [])) if extraction_data else 0

            # Se houve erro na extracao, marcar como falha (o _extract_data deixa o erro cru)
            if extraction_data is None or (
                not extraction_data.get("items") and document.error_message
            ):
                mark_failure(document, document.error_message)
            else:
                mark_completed(document)
                logger.info(
                    "document_processing_completed document_id=%s item_count=%s",
                    document.id,
                    items_count,
                )

            document.processed_at = utc_now()
            await self.db.flush()
            await self.db.refresh(document)

            return extraction_data

        except AIUnavailable:
            raise

        except Exception as e:
            logger.error(
                "document_processing_failed document_id=%s error_type=%s",
                document.id,
                type(e).__name__,
            )

            mark_failure(document, e)
            await self.db.flush()
            await self.db.refresh(document)
            return None

    @metered("extraction", document_arg="document")
    async def _extract_data(
        self, document: Document, content: bytes, password: str | None = None
    ) -> dict | None:
        """Extrai dados do documento usando LLM com visao ou parser de planilha

        Args:
            document: Document model instance
            content: File content as bytes
            password: Optional password for protected PDFs
        """

        # Verificar se e CSV ou Excel
        mime_type = document.mime_type or ""
        filename = document.original_filename or ""

        is_spreadsheet = mime_type in [
            "text/csv",
            "application/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ] or filename.lower().endswith((".csv", ".xlsx", ".xls"))

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
            if selected_provider == "deepseek" and settings.deepseek_api_key:
                selected_model = settings.vision_model
            elif selected_provider == "mistral" and settings.mistral_api_key:
                selected_model = settings.mistral_llm_model
            elif selected_provider == "google" and settings.google_api_key:
                selected_model = settings.vision_model
            elif settings.deepseek_api_key:
                selected_provider = "deepseek"
                selected_model = settings.vision_model
            elif settings.google_api_key:
                selected_provider = "google"
                selected_model = settings.vision_model
            elif settings.mistral_api_key:
                selected_provider = "mistral"
                selected_model = settings.mistral_llm_model
            else:
                selected_provider = settings.vision_provider
                selected_model = settings.vision_model
            logger.info("[DOC_SVC] Using %s for extraction", selected_provider)

            from app.modules.documents.services.llm_ocr_service import LLMOCRService

            llm_service = LLMOCRService(provider=selected_provider, model=selected_model)
            result = await llm_service.extract_from_image(
                content, mime_type, filename=filename, password=password
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
            logger.error("_check_duplicates_batch_failed error_type=%s", type(e).__name__)
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
