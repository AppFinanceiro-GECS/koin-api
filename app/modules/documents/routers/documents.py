from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile

from app.core.deps import CurrentUser, DbSession
from app.modules.documents.schemas.document import DocumentAsyncUploadResponse, DocumentResponse
from app.modules.documents.services.document_service import DocumentService, PasswordRequiredError

router = APIRouter()


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    credit_card_id: int | None = Form(None),
):
    """
    Upload de documento (foto/PDF) para processamento SINCRONO.
    Retorna dados extraidos para confirmacao (nao salva automaticamente).
    Inclui alerta is_duplicate se documento ja foi enviado antes.

    NOTA: Para melhor UX, use POST /documents/async que retorna imediatamente.

    Args:
        file: PDF or image file
        password: Optional password for protected PDFs
        credit_card_id: Optional credit card ID to use saved password automatically
    """
    # Debug: log password info (not the password itself!)
    if password:
        print(
            f"[UPLOAD] Password received - length: {len(password)}, repr: {repr(password[:3])}..."
        )

    service = DocumentService(db)
    try:
        # Service agora retorna DocumentResponse diretamente
        return await service.upload(current_user, file, password, credit_card_id)
    except PasswordRequiredError:
        raise HTTPException(
            status_code=422,
            detail={"error": "password_required", "message": "PDF protegido por senha"},
        )


@router.post("/async", response_model=DocumentAsyncUploadResponse, status_code=202)
async def upload_document_async(
    current_user: CurrentUser,
    db: DbSession,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    password: str | None = Form(None),
    credit_card_id: int | None = Form(None),
):
    """
    Upload de documento (foto/PDF) para processamento ASSINCRONO.
    Retorna imediatamente com status "processing".
    Use GET /documents/{id} para verificar status e obter dados extraidos.

    Args:
        file: PDF or image file
        password: Optional password for protected PDFs
        credit_card_id: Optional credit card ID to use saved password automatically
    """
    service = DocumentService(db)
    try:
        return await service.upload_async(
            current_user, file, background_tasks, password, credit_card_id
        )
    except PasswordRequiredError:
        raise HTTPException(
            status_code=422,
            detail={"error": "password_required", "message": "PDF protegido por senha"},
        )


@router.post("/batch", response_model=DocumentResponse, status_code=201)
async def upload_documents_batch(
    current_user: CurrentUser,
    db: DbSession,
    files: list[UploadFile] = File(...),
):
    """
    Upload de multiplas imagens como 1 documento (para cupons grandes).
    Permite enviar ate 10 imagens que serao processadas como um unico documento.
    Util para cupons fiscais ou faturas que nao cabem em uma unica foto.
    """
    service = DocumentService(db)
    return await service.upload_batch(current_user, files)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
):
    """Lista documentos do usuario"""
    service = DocumentService(db)
    return await service.list(current_user, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Retorna documento com status e dados extraidos.
    Use para polling apos upload async.
    """
    service = DocumentService(db)
    document = await service.get_by_id(current_user, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento nao encontrado")

    # Se documento foi processado em background, converter dados salvos
    response = DocumentResponse.model_validate(document)

    # Se tem extracted_data salvo (processamento async), converter para response
    if document.extracted_data and document.status == "completed":
        from app.modules.documents.schemas.document import (
            CardInfoResponse,
            DetectedPaymentResponse,
            ExtractedItemResponse,
            FutureInstallmentResponse,
            PaymentInfoResponse,
        )
        from app.modules.known_services.schemas.recurring_detection import RecurringDetection
        from app.modules.known_services.services.recurring_detector import RecurringDetectorService

        extraction_data = document.extracted_data
        items = extraction_data.get("items", [])

        # Detectar recorrencias
        recurring_detector = RecurringDetectorService(db)
        card_info = extraction_data.get("card_info", {})
        invoice_month = card_info.get("invoice_month") if card_info else None
        invoice_year = card_info.get("invoice_year") if card_info else None

        items_with_detection = await recurring_detector.detect_all(
            user=current_user,
            items=items,
            invoice_month=invoice_month,
            invoice_year=invoice_year,
        )

        # Filtrar itens com valor != 0
        valid_items = [item for item in items_with_detection if item.get("amount", 0) != 0]

        # Verificar duplicatas em batch
        items_for_dup_check = [
            (item.get("description", "Item"), item.get("amount", 0), item.get("date"))
            for item in valid_items
        ]
        duplicate_results = await service._check_duplicates_batch(current_user, items_for_dup_check)

        extracted_items = []
        for idx, item in enumerate(valid_items):
            duplicate_info = (
                duplicate_results[idx]
                if idx < len(duplicate_results)
                else {"is_duplicate": False, "transaction_id": None}
            )

            future_installments = None
            if item.get("future_installments"):
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
                    future_installments=future_installments,
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

        # Card info
        if card_info:
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

        # Payment info
        payment_info = extraction_data.get("payment_info")
        if payment_info:
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

    # Fallback: se tem extractions antigas
    elif document.extractions:
        from app.modules.documents.schemas.document import DocumentExtractionResponse

        response.extraction = DocumentExtractionResponse.model_validate(document.extractions[0])

    return response


@router.post("/{document_id}/retry", response_model=DocumentResponse)
async def retry_document_processing(
    document_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Reprocessa documento que falhou"""
    service = DocumentService(db)
    return await service.retry_processing(current_user, document_id)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove documento e arquivo associado"""
    service = DocumentService(db)
    await service.delete(current_user, document_id)
