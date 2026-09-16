from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.balance_monitor import BalanceMonitor
from app.core.utils import utc_now
from app.models.account import Account
from app.models.benefit_card import BenefitCard
from app.models.credit_card import CreditCard
from app.models.document import Document
from app.models.grocery import GroceryCategory, GroceryPurchase, NecessityType
from app.models.receipt import Receipt, ReceiptPayment, ReceiptStatus
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.modules.credit_cards.services.invoice_service import InvoiceService
from app.modules.installments.services.installment_service import InstallmentService
from app.modules.receipts.schemas.receipt import (
    ReceiptConfirmRequest,
    ReceiptListResponse,
    ReceiptPaymentResponse,
    ReceiptResponse,
    ReceiptUpdate,
)


class ReceiptService:
    """Serviço para gerenciar receipts e pagamentos"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== CRUD ====================

    async def confirm_receipt(self, user: User, data: ReceiptConfirmRequest) -> ReceiptResponse:
        """
        Confirma um receipt a partir dos dados extraídos do documento.
        Cria o Receipt, os ReceiptPayments e as Transactions vinculadas.
        """
        # 1. Verificar se o document existe e pertence ao usuário
        doc_result = await self.db.execute(
            select(Document).where(
                Document.id == data.document_id,
                Document.user_id == user.id,
            )
        )
        document = doc_result.scalar_one_or_none()
        if not document:
            raise HTTPException(status_code=404, detail="Documento não encontrado")

        # 2. Verificar se já existe um receipt para este documento
        existing_result = await self.db.execute(
            select(Receipt).where(Receipt.document_id == data.document_id)
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Já existe um receipt para este documento")

        # 3. Validar accounts pertencem ao usuário
        account_ids = [p.account_id for p in data.payments]
        accounts_result = await self.db.execute(
            select(Account).where(
                Account.id.in_(account_ids),
                Account.user_id == user.id,
            )
        )
        valid_accounts = {a.id: a for a in accounts_result.scalars().all()}
        for account_id in account_ids:
            if account_id not in valid_accounts:
                raise HTTPException(
                    status_code=400,
                    detail=f"Conta {account_id} não encontrada ou não pertence ao usuário",
                )

        # 4. Validar benefit cards (se fornecidos)
        benefit_card_ids = [p.benefit_card_id for p in data.payments if p.benefit_card_id]
        if benefit_card_ids:
            cards_result = await self.db.execute(
                select(BenefitCard).where(
                    BenefitCard.id.in_(benefit_card_ids),
                    BenefitCard.user_id == user.id,
                )
            )
            valid_cards = {c.id for c in cards_result.scalars().all()}
            for card_id in benefit_card_ids:
                if card_id not in valid_cards:
                    raise HTTPException(
                        status_code=400, detail=f"Cartão de benefício {card_id} não encontrado"
                    )

        # 4.1. Validar credit cards (para pagamentos parcelados)
        credit_card_ids = [p.credit_card_id for p in data.payments if p.credit_card_id]
        valid_credit_cards: dict[int, CreditCard] = {}
        if credit_card_ids:
            cc_result = await self.db.execute(
                select(CreditCard).where(
                    CreditCard.id.in_(credit_card_ids),
                    CreditCard.user_id == user.id,
                )
            )
            valid_credit_cards = {c.id: c for c in cc_result.scalars().all()}
            for cc_id in credit_card_ids:
                if cc_id not in valid_credit_cards:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cartão de crédito {cc_id} não encontrado ou não pertence ao usuário",
                    )

        # 5. Criar o Receipt
        receipt = Receipt(
            user_id=user.id,
            document_id=data.document_id,
            store_name=data.store_name,
            store_cnpj=data.store_cnpj,
            purchase_date=data.purchase_date,
            total_amount=data.total_amount,
            subtotal=data.subtotal,
            discount=data.discount,
            status=ReceiptStatus.CONFIRMED.value,
            confirmed_at=utc_now(),
        )
        self.db.add(receipt)
        await self.db.flush()  # Para obter o ID

        # 6. Criar os ReceiptPayments e atualizar saldos das contas
        # Inicializar serviços para parcelamento
        installment_service = InstallmentService(self.db)
        invoice_service = InvoiceService(self.db)

        for idx, payment_data in enumerate(data.payments, 1):
            payment = ReceiptPayment(
                receipt_id=receipt.id,
                account_id=payment_data.account_id,
                benefit_card_id=payment_data.benefit_card_id,
                payment_method=payment_data.payment_method,
                amount=payment_data.amount,
                sequence=idx,
                original_label=payment_data.original_label,
                is_installment=payment_data.is_installment,
                installment_count=payment_data.installment_count
                if payment_data.is_installment
                else None,
                credit_card_id=payment_data.credit_card_id if payment_data.is_installment else None,
            )
            self.db.add(payment)
            await self.db.flush()  # Para obter o ID do payment

            # Se é pagamento parcelado, criar série de parcelas
            if payment_data.is_installment and payment_data.credit_card_id:
                credit_card = valid_credit_cards[payment_data.credit_card_id]
                installment_amount = float(payment_data.amount) / payment_data.installment_count

                # Criar a série de parcelas
                series = await installment_service.create_series(
                    user=user,
                    description=f"{data.store_name} - Parcelado",
                    merchant_name=data.store_name,
                    installment_amount=installment_amount,
                    installment_count=payment_data.installment_count,
                    first_installment_date=data.purchase_date,
                    account_id=credit_card.account_id,
                    category_id=data.default_category_id,
                    purchase_date=data.purchase_date,
                    credit_card_id=credit_card.id,
                )

                # Vincular série ao payment
                payment.installment_series_id = series.id

                # Calcular o período da fatura para a primeira parcela
                period = invoice_service.calculate_invoice_period(credit_card, data.purchase_date)

                # Obter/criar a fatura para a primeira parcela
                first_invoice = await invoice_service.get_or_create_invoice(
                    user=user,
                    credit_card=credit_card,
                    reference_month=period["reference_month"],
                    reference_year=period["reference_year"],
                    closing_date=period["closing_date"],
                    due_date=period["due_date"],
                )

                # Criar transação da primeira parcela
                first_installment_tx = await installment_service.create_installment_transaction(
                    user=user,
                    series=series,
                    installment_number=1,
                    transaction_date=data.purchase_date,
                    is_paid=False,  # Parcela futura (vai para fatura)
                    document_id=data.document_id,
                    credit_card_id=credit_card.id,
                    invoice_id=first_invoice.id,
                )

                # Vincular transação à série como first_transaction
                series.first_transaction_id = first_installment_tx.id

                # Criar parcelas futuras
                await installment_service.create_future_installments(
                    user=user,
                    series=series,
                    from_installment=1,
                    current_invoice_month=period["reference_month"],
                    current_invoice_year=period["reference_year"],
                )

                # Atualizar total da fatura da primeira parcela
                await invoice_service.update_invoice_total(first_invoice)

                # NÃO deduzir saldo da conta - parcelas vão para as faturas
            else:
                # Atualizar saldo da conta (deduzir o valor do pagamento)
                account = valid_accounts[payment_data.account_id]

                # MONITOR: Verificar se resultará em saldo negativo (ALERTA, não bloqueia)
                check_result = BalanceMonitor.check_negative_balance(
                    account, payment_data.amount, f"pagamento de recibo #{receipt.id}"
                )

                if check_result["will_be_negative"]:
                    # LOG: Registrar evento para auditoria
                    BalanceMonitor.log_negative_balance_event(
                        account, payment_data.amount, f"receipt_payment #{payment.id}", user.id
                    )
                    print(check_result["alert_message"])

                # Realizar débito (PERMITE saldo negativo - cartão físico tem saldo real)
                account.balance = float(account.balance) - float(payment_data.amount)

        # 7. Criar as Transactions vinculadas ao receipt
        # Transações de receipt NÃO têm account_id - o saldo vem dos ReceiptPayments
        for item in data.items:
            transaction = Transaction(
                user_id=user.id,
                account_id=list(valid_accounts.keys())[0],  # Conta principal (primeira)
                receipt_id=receipt.id,
                document_id=data.document_id,
                type=TransactionType.EXPENSE.value,
                amount=float(item.amount),
                date=data.purchase_date,
                description=item.description,
                category_id=item.category_id or data.default_category_id,
            )
            self.db.add(transaction)

        # 8. Criar GroceryPurchases para cada item (para tela de Mercado)
        for item in data.items:
            quantity = float(item.quantity) if item.quantity else 1.0
            unit = item.unit or "un"
            unit_price = float(item.unit_price) if item.unit_price else float(item.amount)
            total_price = float(item.amount)

            grocery_purchase = GroceryPurchase(
                user_id=user.id,
                receipt_id=receipt.id,
                document_id=data.document_id,
                product_name=item.description,
                quantity=quantity,
                unit=unit,
                unit_price=unit_price,
                total_price=total_price,
                category=item.grocery_category or GroceryCategory.OTHER.value,
                necessity_type=item.necessity_type or NecessityType.ESSENTIAL.value,
                purchase_date=data.purchase_date,
                ownership_type="household",
            )
            self.db.add(grocery_purchase)

        await self.db.commit()
        await self.db.refresh(receipt)

        return await self.get_receipt(user, receipt.id)

    async def list_receipts(
        self,
        user: User,
        limit: int = 20,
        offset: int = 0,
        status: ReceiptStatus | None = None,
    ) -> list[ReceiptListResponse]:
        """Lista receipts do usuário"""
        query = (
            select(Receipt)
            .where(Receipt.user_id == user.id)
            .order_by(Receipt.purchase_date.desc(), Receipt.id.desc())
        )

        if status:
            query = query.where(Receipt.status == status.value)

        query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        receipts = result.scalars().all()

        # Buscar contagem de itens e pagamentos
        response_list = []
        for receipt in receipts:
            # Contagem de itens
            items_result = await self.db.execute(
                select(func.count(Transaction.id)).where(Transaction.receipt_id == receipt.id)
            )
            items_count = items_result.scalar() or 0

            # Contagem de pagamentos
            payments_result = await self.db.execute(
                select(func.count(ReceiptPayment.id)).where(ReceiptPayment.receipt_id == receipt.id)
            )
            payments_count = payments_result.scalar() or 0

            response_list.append(
                ReceiptListResponse(
                    id=receipt.id,
                    document_id=receipt.document_id,
                    store_name=receipt.store_name,
                    purchase_date=receipt.purchase_date,
                    total_amount=float(receipt.total_amount),
                    status=receipt.status,
                    status_display=receipt.status_display,
                    items_count=items_count,
                    payments_count=payments_count,
                    has_split_payment=payments_count > 1,
                    created_at=receipt.created_at,
                )
            )

        return response_list

    async def get_receipt(self, user: User, receipt_id: int) -> ReceiptResponse:
        """Retorna um receipt específico com todos os detalhes"""
        result = await self.db.execute(
            select(Receipt)
            .options(selectinload(Receipt.payments).selectinload(ReceiptPayment.account))
            .options(selectinload(Receipt.payments).selectinload(ReceiptPayment.benefit_card))
            .where(
                Receipt.id == receipt_id,
                Receipt.user_id == user.id,
            )
        )
        receipt = result.scalar_one_or_none()
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt não encontrado")

        # Contagem de itens
        items_result = await self.db.execute(
            select(func.count(Transaction.id)).where(Transaction.receipt_id == receipt.id)
        )
        items_count = items_result.scalar() or 0

        # Montar resposta de pagamentos
        payments_response = []
        for payment in receipt.payments:
            account_name = payment.account.name if payment.account else None
            benefit_card_name = None
            if payment.benefit_card and payment.benefit_card.account:
                benefit_card_name = payment.benefit_card.account.name

            payments_response.append(
                ReceiptPaymentResponse(
                    id=payment.id,
                    payment_method=payment.payment_method,
                    amount=float(payment.amount),
                    account_id=payment.account_id,
                    account_name=account_name,
                    benefit_card_id=payment.benefit_card_id,
                    benefit_card_name=benefit_card_name,
                    sequence=payment.sequence,
                    original_label=payment.original_label,
                    is_installment=payment.is_installment,
                    installment_count=payment.installment_count,
                    credit_card_id=payment.credit_card_id,
                    installment_series_id=payment.installment_series_id,
                )
            )

        return ReceiptResponse(
            id=receipt.id,
            document_id=receipt.document_id,
            store_name=receipt.store_name,
            store_cnpj=receipt.store_cnpj,
            purchase_date=receipt.purchase_date,
            total_amount=float(receipt.total_amount),
            subtotal=float(receipt.subtotal) if receipt.subtotal else None,
            discount=float(receipt.discount) if receipt.discount else None,
            status=receipt.status,
            status_display=receipt.status_display,
            created_at=receipt.created_at,
            confirmed_at=receipt.confirmed_at,
            items_count=items_count,
            payments_count=len(receipt.payments),
            has_split_payment=len(receipt.payments) > 1,
            payments=payments_response,
        )

    async def get_receipt_items(self, user: User, receipt_id: int) -> list[dict]:
        """Retorna as transações (itens) de um receipt"""
        # Verificar se o receipt existe e pertence ao usuário
        receipt_result = await self.db.execute(
            select(Receipt).where(
                Receipt.id == receipt_id,
                Receipt.user_id == user.id,
            )
        )
        if not receipt_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Receipt não encontrado")

        # Buscar transações
        result = await self.db.execute(
            select(Transaction).where(Transaction.receipt_id == receipt_id).order_by(Transaction.id)
        )
        transactions = result.scalars().all()

        return [
            {
                "id": t.id,
                "description": t.description,
                "amount": float(t.amount),
                "category_id": t.category_id,
                "date": t.date,
            }
            for t in transactions
        ]

    async def update_receipt(
        self, user: User, receipt_id: int, data: ReceiptUpdate
    ) -> ReceiptResponse:
        """Atualiza dados de um receipt"""
        result = await self.db.execute(
            select(Receipt).where(
                Receipt.id == receipt_id,
                Receipt.user_id == user.id,
            )
        )
        receipt = result.scalar_one_or_none()
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt não encontrado")

        # Atualizar campos
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(receipt, field, value)

        await self.db.commit()
        await self.db.refresh(receipt)

        return await self.get_receipt(user, receipt_id)

    async def cancel_receipt(self, user: User, receipt_id: int) -> None:
        """Cancela um receipt (soft delete)"""
        result = await self.db.execute(
            select(Receipt).where(
                Receipt.id == receipt_id,
                Receipt.user_id == user.id,
            )
        )
        receipt = result.scalar_one_or_none()
        if not receipt:
            raise HTTPException(status_code=404, detail="Receipt não encontrado")

        # Desvincular transações (não deletar)
        await self.db.execute(select(Transaction).where(Transaction.receipt_id == receipt_id))
        # Atualizar transações para remover vínculo
        from sqlalchemy import update

        await self.db.execute(
            update(Transaction).where(Transaction.receipt_id == receipt_id).values(receipt_id=None)
        )

        # Marcar como cancelado
        receipt.status = ReceiptStatus.CANCELLED.value
        await self.db.commit()

    # ==================== BALANCE CALCULATION ====================

    async def calculate_receipt_payments_total(
        self, account_id: int, confirmed_only: bool = True
    ) -> Decimal:
        """
        Calcula o total de pagamentos de receipts para uma conta.
        Usado para cálculo de saldo da conta.
        """
        query = (
            select(func.coalesce(func.sum(ReceiptPayment.amount), 0))
            .select_from(ReceiptPayment)
            .join(Receipt)
            .where(ReceiptPayment.account_id == account_id)
        )

        if confirmed_only:
            query = query.where(Receipt.status == ReceiptStatus.CONFIRMED.value)

        result = await self.db.execute(query)
        return Decimal(str(result.scalar() or 0))
