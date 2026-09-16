"""
Serviço de Gestão de Dívidas (Debt)
Implementa metodologias Dave Ramsey (Snowball/Avalanche) e Gustavo Cerbasi
"""

from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.debt import Debt, DebtPayment, DebtStatus, DebtType
from app.models.user import User
from app.modules.debts.schemas.debt import (
    AvalanchePlan,
    DebtCreate,
    DebtDetailResponse,
    DebtHighlight,
    DebtPaymentCreate,
    DebtPaymentResponse,
    DebtPayoffProjection,
    DebtResponse,
    DebtSummary,
    DebtUpdate,
    PayoffStrategyComparison,
    SnowballDebtStep,
    SnowballPlan,
)
from app.modules.household.utils import (
    build_ownership_filter,
    get_household_member,
    get_household_user_ids,
    validate_create_permission,
    validate_delete_permission,
    validate_edit_permission,
)


class DebtService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_debts(
        self, user: User, status_filter: DebtStatus | None = None
    ) -> list[DebtResponse]:
        """Lista dívidas do usuário (personal + household da família)"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        query = select(Debt).where(
            build_ownership_filter(
                Debt, Debt.user_id, Debt.ownership_type, user.id, household_user_ids, member
            )
        )

        if status_filter:
            query = query.where(Debt.status == status_filter.value)

        query = query.order_by(Debt.priority.desc(), Debt.current_balance.desc())
        result = await self.db.execute(query)
        debts = result.scalars().all()

        return [self._build_debt_response(debt) for debt in debts]

    async def get_debt(self, user: User, debt_id: int) -> DebtDetailResponse | None:
        """Retorna dívida com detalhes e projeção"""
        result = await self.db.execute(
            select(Debt).where(Debt.id == debt_id, Debt.user_id == user.id)
        )
        debt = result.scalar_one_or_none()

        if not debt:
            return None

        response = self._build_debt_response(debt)
        payments = [
            DebtPaymentResponse(
                id=p.id,
                debt_id=p.debt_id,
                amount=p.amount,
                principal_amount=p.principal_amount,
                interest_amount=p.interest_amount,
                payment_date=p.payment_date,
                notes=p.notes,
                transaction_id=p.transaction_id,
                created_at=p.created_at,
            )
            for p in debt.payments
        ]

        projection = self._calculate_payoff_projection(debt)

        return DebtDetailResponse(
            **response.model_dump(), payments=payments, payoff_projection=projection
        )

    async def create_debt(self, user: User, data: DebtCreate) -> Debt:
        """Cria nova dívida"""
        # Validar permissão para criar household
        await validate_create_permission(self.db, user, data.ownership_type.value)

        debt = Debt(
            user_id=user.id,
            name=data.name,
            description=data.description,
            type=data.type.value,
            creditor=data.creditor,
            original_amount=data.original_amount,
            current_balance=data.current_balance,
            minimum_payment=data.minimum_payment,
            interest_rate=data.interest_rate,
            interest_type=data.interest_type,
            start_date=data.start_date,
            due_day=data.due_day,
            priority=data.priority,
            account_id=data.account_id,
            installment_series_id=data.installment_series_id,
            ownership_type=data.ownership_type.value,
        )

        # Calcular data prevista de quitação
        if debt.minimum_payment > 0:
            projection = self._calculate_payoff_projection(debt)
            if projection:
                debt.expected_payoff_date = projection.payoff_date_if_minimum

        self.db.add(debt)
        await self.db.flush()
        await self.db.refresh(debt)
        return debt

    async def update_debt(self, user: User, debt_id: int, data: DebtUpdate) -> Debt:
        """Atualiza dívida"""
        result = await self.db.execute(
            select(Debt).where(Debt.id == debt_id, Debt.user_id == user.id)
        )
        debt = result.scalar_one_or_none()

        if not debt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dívida não encontrada"
            )

        # Validar permissão para editar
        await validate_edit_permission(self.db, user, debt.user_id, debt.ownership_type)

        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "status" and value:
                value = value.value
            if field == "type" and value:
                value = value.value
            setattr(debt, field, value)

        # Marcar como quitada se saldo zerou
        if debt.current_balance <= 0 and debt.status == DebtStatus.ACTIVE.value:
            debt.status = DebtStatus.PAID_OFF.value
            debt.paid_off_date = date.today()
            debt.current_balance = Decimal(0)

        await self.db.flush()
        await self.db.refresh(debt)
        return debt

    async def delete_debt(self, user: User, debt_id: int) -> None:
        """Remove dívida"""
        result = await self.db.execute(
            select(Debt).where(Debt.id == debt_id, Debt.user_id == user.id)
        )
        debt = result.scalar_one_or_none()

        if not debt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dívida não encontrada"
            )

        # Validar permissão para deletar
        await validate_delete_permission(self.db, user, debt.user_id, debt.ownership_type)

        await self.db.delete(debt)

    async def add_payment(self, user: User, debt_id: int, data: DebtPaymentCreate) -> DebtPayment:
        """Registra pagamento de dívida"""
        result = await self.db.execute(
            select(Debt).where(Debt.id == debt_id, Debt.user_id == user.id)
        )
        debt = result.scalar_one_or_none()

        if not debt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dívida não encontrada"
            )

        # Calcular divisão entre principal e juros se não informado
        principal = data.principal_amount
        interest = data.interest_amount

        if principal == 0 and interest == 0:
            # Estimar: primeiro paga juros, depois principal
            monthly_interest = debt.monthly_interest_amount
            if data.amount > monthly_interest:
                interest = monthly_interest
                principal = data.amount - monthly_interest
            else:
                interest = data.amount
                principal = Decimal(0)

        payment = DebtPayment(
            debt_id=debt.id,
            amount=data.amount,
            principal_amount=principal,
            interest_amount=interest,
            payment_date=data.payment_date,
            notes=data.notes,
            transaction_id=data.transaction_id,
        )
        self.db.add(payment)

        # Atualizar saldo da dívida
        debt.current_balance = max(Decimal(0), debt.current_balance - principal)

        # Verificar se quitou
        if debt.current_balance <= 0:
            debt.status = DebtStatus.PAID_OFF.value
            debt.paid_off_date = date.today()

        await self.db.flush()
        await self.db.refresh(payment)
        return payment

    async def get_summary(self, user: User) -> DebtSummary:
        """Retorna resumo de todas as dívidas"""
        result = await self.db.execute(select(Debt).where(Debt.user_id == user.id))
        debts = result.scalars().all()

        active = [d for d in debts if d.status == DebtStatus.ACTIVE.value]
        paid_off = [d for d in debts if d.status == DebtStatus.PAID_OFF.value]

        total_owed = sum(d.current_balance for d in active)
        total_minimum = sum(d.minimum_payment for d in active)
        total_interest = sum(d.monthly_interest_amount for d in active)

        # Encontrar dívida com maior juros
        highest_interest = None
        if active:
            highest = max(active, key=lambda d: d.interest_rate)
            highest_interest = DebtHighlight(
                debt_id=highest.id,
                name=highest.name,
                balance=highest.current_balance,
                interest_rate=highest.interest_rate,
                monthly_interest=highest.monthly_interest_amount,
            )

        # Encontrar dívida com menor saldo
        smallest_balance = None
        if active:
            smallest = min(active, key=lambda d: d.current_balance)
            smallest_balance = DebtHighlight(
                debt_id=smallest.id,
                name=smallest.name,
                balance=smallest.current_balance,
                interest_rate=smallest.interest_rate,
                monthly_interest=smallest.monthly_interest_amount,
            )

        # Estimar data livre de dívidas (método avalanche simplificado)
        debt_free_date = None
        if active and total_minimum > 0:
            # Estimativa simples: saldo total / pagamento total mensal
            months = int(total_owed / total_minimum) + 1
            debt_free_date = date.today() + relativedelta(months=months)

        return DebtSummary(
            total_debts=len(debts),
            active_debts=len(active),
            paid_off_debts=len(paid_off),
            total_owed=total_owed,
            total_minimum_payments=total_minimum,
            total_interest_monthly=total_interest,
            highest_interest_debt=highest_interest,
            smallest_balance_debt=smallest_balance,
            debt_free_date=debt_free_date,
        )

    async def get_snowball_plan(self, user: User, monthly_payment: Decimal) -> SnowballPlan:
        """
        Gera plano de quitação pelo método Snowball (Dave Ramsey)
        Ordena dívidas do menor para maior saldo
        """
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        result = await self.db.execute(
            select(Debt)
            .where(
                Debt.status == DebtStatus.ACTIVE.value,
                build_ownership_filter(
                    Debt, Debt.user_id, Debt.ownership_type, user.id, household_user_ids, member
                ),
            )
            .order_by(Debt.current_balance.asc())
        )
        debts = list(result.scalars().all())

        return self._simulate_payoff(debts, monthly_payment, "snowball")

    async def get_avalanche_plan(self, user: User, monthly_payment: Decimal) -> AvalanchePlan:
        """
        Gera plano de quitação pelo método Avalanche
        Ordena dívidas da maior para menor taxa de juros
        """
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        result = await self.db.execute(
            select(Debt)
            .where(
                Debt.status == DebtStatus.ACTIVE.value,
                build_ownership_filter(
                    Debt, Debt.user_id, Debt.ownership_type, user.id, household_user_ids, member
                ),
            )
            .order_by(Debt.interest_rate.desc())
        )
        debts = list(result.scalars().all())

        return self._simulate_payoff(debts, monthly_payment, "avalanche")

    async def compare_strategies(
        self, user: User, monthly_payment: Decimal
    ) -> PayoffStrategyComparison:
        """Compara estratégias Snowball e Avalanche"""
        snowball = await self.get_snowball_plan(user, monthly_payment)
        avalanche = await self.get_avalanche_plan(user, monthly_payment)

        months_diff = snowball.total_months - avalanche.total_months
        interest_diff = snowball.total_interest - avalanche.total_interest

        # Recomendar avalanche se economia de juros > 10% ou > 3 meses
        if interest_diff > snowball.total_interest * Decimal("0.1") or months_diff > 3:
            recommendation = "avalanche"
            reason = f"Economiza R$ {interest_diff:.2f} em juros e {abs(months_diff)} meses"
        else:
            recommendation = "snowball"
            reason = "Vitórias rápidas motivam a continuar. Diferença de juros é pequena."

        return PayoffStrategyComparison(
            snowball=snowball,
            avalanche=AvalanchePlan(
                strategy="avalanche",
                monthly_payment=avalanche.monthly_payment,
                debts_order=avalanche.debts_order,
                total_months=avalanche.total_months,
                total_interest=avalanche.total_interest,
                debt_free_date=avalanche.debt_free_date,
                interest_saved_vs_snowball=interest_diff,
            ),
            recommendation=recommendation,
            recommendation_reason=reason,
            months_difference=months_diff,
            interest_difference=interest_diff,
        )

    def _build_debt_response(self, debt: Debt) -> DebtResponse:
        """Constrói resposta com campos calculados"""
        total_paid = debt.total_paid
        progress = debt.progress_percentage
        monthly_interest = debt.monthly_interest_amount

        # Calcular próxima data de pagamento
        next_payment_date = None
        if debt.due_day and debt.status == DebtStatus.ACTIVE.value:
            today = date.today()
            next_payment = date(today.year, today.month, min(debt.due_day, 28))
            if next_payment <= today:
                next_payment = next_payment + relativedelta(months=1)
            next_payment_date = next_payment

        return DebtResponse(
            id=debt.id,
            user_id=debt.user_id,
            name=debt.name,
            description=debt.description,
            type=DebtType(debt.type),
            creditor=debt.creditor,
            original_amount=debt.original_amount,
            current_balance=debt.current_balance,
            minimum_payment=debt.minimum_payment,
            interest_rate=debt.interest_rate,
            interest_type=debt.interest_type,
            start_date=debt.start_date,
            due_day=debt.due_day,
            priority=debt.priority,
            account_id=debt.account_id,
            installment_series_id=debt.installment_series_id,
            status=DebtStatus(debt.status),
            expected_payoff_date=debt.expected_payoff_date,
            paid_off_date=debt.paid_off_date,
            created_at=debt.created_at,
            updated_at=debt.updated_at,
            total_paid=total_paid,
            progress_percentage=progress,
            monthly_interest_amount=monthly_interest,
            next_payment_date=next_payment_date,
        )

    def _calculate_payoff_projection(
        self, debt: Debt, extra_payment: Decimal = Decimal(0)
    ) -> DebtPayoffProjection | None:
        """Calcula projeção de quitação da dívida"""
        if debt.current_balance <= 0:
            return None

        if debt.minimum_payment <= 0:
            return DebtPayoffProjection(
                months_to_payoff=0,
                total_interest_if_minimum=Decimal(0),
                total_paid_if_minimum=debt.current_balance,
                payoff_date_if_minimum=date.today(),
            )

        # Simular pagamento mínimo
        balance = debt.current_balance
        monthly_rate = self._get_monthly_rate(debt)
        months = 0
        total_interest = Decimal(0)
        total_paid = Decimal(0)

        while balance > 0 and months < 360:  # Max 30 anos
            interest = balance * monthly_rate
            total_interest += interest
            balance += interest

            payment = min(debt.minimum_payment, balance)
            balance -= payment
            total_paid += payment
            months += 1

        payoff_date = date.today() + relativedelta(months=months)

        result = DebtPayoffProjection(
            months_to_payoff=months,
            total_interest_if_minimum=total_interest,
            total_paid_if_minimum=total_paid,
            payoff_date_if_minimum=payoff_date,
        )

        # Calcular com pagamento extra se fornecido
        if extra_payment > 0:
            balance = debt.current_balance
            extra_months = 0
            extra_interest = Decimal(0)

            while balance > 0 and extra_months < 360:
                interest = balance * monthly_rate
                extra_interest += interest
                balance += interest

                payment = min(debt.minimum_payment + extra_payment, balance)
                balance -= payment
                extra_months += 1

            result.extra_payment = extra_payment
            result.months_saved = months - extra_months
            result.interest_saved = total_interest - extra_interest
            result.payoff_date_with_extra = date.today() + relativedelta(months=extra_months)

        return result

    def _simulate_payoff(
        self, debts: list[Debt], monthly_payment: Decimal, strategy: str
    ) -> SnowballPlan:
        """Simula plano de quitação para lista ordenada de dívidas"""
        if not debts:
            return SnowballPlan(
                strategy=strategy,
                monthly_payment=monthly_payment,
                debts_order=[],
                total_months=0,
                total_interest=Decimal(0),
                debt_free_date=date.today(),
            )

        # Inicializar saldos
        balances = {d.id: d.current_balance for d in debts}
        rates = {d.id: self._get_monthly_rate(d) for d in debts}
        minimums = {d.id: d.minimum_payment for d in debts}

        steps = []
        total_months = 0
        total_interest = Decimal(0)
        order = 0

        for debt in debts:
            if balances[debt.id] <= 0:
                continue

            order += 1
            debt_months = 0
            debt_interest = Decimal(0)
            starting_balance = balances[debt.id]

            # Calcular pagamento disponível (mínimo de outras + sobra)
            while balances[debt.id] > 0:
                # Aplicar juros a todas as dívidas ativas
                for d in debts:
                    if balances[d.id] > 0:
                        interest = balances[d.id] * rates[d.id]
                        balances[d.id] += interest
                        if d.id == debt.id:
                            debt_interest += interest
                        total_interest += interest

                # Pagar mínimo de outras dívidas
                other_minimums = sum(
                    min(minimums[d.id], balances[d.id])
                    for d in debts
                    if d.id != debt.id and balances[d.id] > 0
                )

                # Resto vai para dívida atual
                available_for_current = monthly_payment - other_minimums
                payment = min(available_for_current, balances[debt.id])
                balances[debt.id] -= payment

                # Pagar mínimo das outras
                for d in debts:
                    if d.id != debt.id and balances[d.id] > 0:
                        other_payment = min(minimums[d.id], balances[d.id])
                        balances[d.id] -= other_payment

                debt_months += 1
                total_months += 1

                if debt_months > 360:  # Safety limit
                    break

            steps.append(
                SnowballDebtStep(
                    debt_id=debt.id,
                    debt_name=debt.name,
                    starting_balance=starting_balance,
                    interest_rate=debt.interest_rate,
                    monthly_payment=monthly_payment - other_minimums
                    if order == 1
                    else monthly_payment,
                    months_to_payoff=debt_months,
                    payoff_date=date.today() + relativedelta(months=total_months),
                    total_interest_paid=debt_interest,
                    order=order,
                )
            )

        return SnowballPlan(
            strategy=strategy,
            monthly_payment=monthly_payment,
            debts_order=steps,
            total_months=total_months,
            total_interest=total_interest,
            debt_free_date=date.today() + relativedelta(months=total_months),
        )

    def _get_monthly_rate(self, debt: Debt) -> Decimal:
        """Retorna taxa de juros mensal"""
        if debt.interest_type == "yearly":
            return debt.interest_rate / 12 / 100
        return debt.interest_rate / 100
