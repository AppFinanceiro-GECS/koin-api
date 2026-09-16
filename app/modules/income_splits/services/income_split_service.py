"""
Service for managing income split rules and applying splits to income transactions.
Creates pending expense transactions linked to the original income.
"""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.income_split_rule import IncomeSplitRule
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.modules.income_splits.schemas.income_split import (
    IncomeSplitPreview,
    IncomeSplitRuleCreate,
    IncomeSplitRuleResponse,
    IncomeSplitRuleUpdate,
)


class IncomeSplitService:
    """Service for managing income split rules"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_rules(self, user: User, active_only: bool = True) -> list[IncomeSplitRule]:
        """
        List all income split rules for a user.

        Args:
            user: The authenticated user
            active_only: If True, only return active rules

        Returns:
            List of income split rules ordered by priority
        """
        filters = [IncomeSplitRule.user_id == user.id]
        if active_only:
            filters.append(IncomeSplitRule.is_active == True)

        result = await self.db.execute(
            select(IncomeSplitRule)
            .where(and_(*filters))
            .order_by(IncomeSplitRule.priority.asc(), IncomeSplitRule.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, user: User, rule_id: int) -> IncomeSplitRule | None:
        """Get a specific income split rule by ID"""
        result = await self.db.execute(
            select(IncomeSplitRule).where(
                IncomeSplitRule.id == rule_id,
                IncomeSplitRule.user_id == user.id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, user: User, data: IncomeSplitRuleCreate) -> IncomeSplitRule:
        """
        Create a new income split rule.

        Args:
            user: The authenticated user
            data: Rule creation data

        Returns:
            The created rule
        """
        rule = IncomeSplitRule(
            user_id=user.id,
            name=data.name,
            split_type=data.split_type.value,
            percentage=data.percentage,
            fixed_amount=data.fixed_amount,
            category_id=data.category_id,
            description_template=data.description_template,
            priority=data.priority,
            is_active=True,
        )
        self.db.add(rule)
        await self.db.flush()
        return rule

    async def update(
        self, user: User, rule_id: int, data: IncomeSplitRuleUpdate
    ) -> IncomeSplitRule | None:
        """
        Update an existing income split rule.

        Args:
            user: The authenticated user
            rule_id: ID of the rule to update
            data: Update data

        Returns:
            The updated rule or None if not found
        """
        rule = await self.get_by_id(user, rule_id)
        if not rule:
            return None

        update_data = data.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field == "split_type" and value:
                value = value.value
            setattr(rule, field, value)

        await self.db.flush()
        return rule

    async def delete(self, user: User, rule_id: int) -> bool:
        """
        Delete an income split rule.

        Args:
            user: The authenticated user
            rule_id: ID of the rule to delete

        Returns:
            True if deleted, False if not found
        """
        rule = await self.get_by_id(user, rule_id)
        if not rule:
            return False

        await self.db.delete(rule)
        return True

    async def preview_splits(
        self,
        user: User,
        income_amount: float,
        rule_ids: list[int] | None = None,
        income_description: str | None = None,
    ) -> list[IncomeSplitPreview]:
        """
        Preview what expenses would be generated for a given income amount.

        Args:
            user: The authenticated user
            income_amount: The income amount to calculate splits from
            rule_ids: Specific rule IDs to preview (None = all active rules)
            income_description: Description of the income for preview

        Returns:
            List of split previews showing calculated amounts
        """
        if rule_ids:
            result = await self.db.execute(
                select(IncomeSplitRule).where(
                    IncomeSplitRule.id.in_(rule_ids),
                    IncomeSplitRule.user_id == user.id,
                    IncomeSplitRule.is_active == True,
                )
            )
        else:
            result = await self.db.execute(
                select(IncomeSplitRule).where(
                    IncomeSplitRule.user_id == user.id,
                    IncomeSplitRule.is_active == True,
                )
            )

        rules = result.scalars().all()
        previews = []

        for rule in rules:
            calculated_amount = rule.calculate_split_amount(income_amount)
            description_preview = rule.format_description(income_description)

            # Get category name if available
            category_name = None
            if rule.category_id:
                cat_result = await self.db.execute(
                    select(Category.name).where(Category.id == rule.category_id)
                )
                category_name = cat_result.scalar_one_or_none()

            previews.append(
                IncomeSplitPreview(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    split_type=rule.split_type,
                    calculated_amount=calculated_amount,
                    category_id=rule.category_id,
                    category_name=category_name,
                    description_preview=description_preview,
                )
            )

        return previews

    async def apply_splits(
        self,
        user: User,
        income_transaction: Transaction,
        rule_ids: list[int],
    ) -> list[Transaction]:
        """
        Apply income split rules to create pending expense transactions.

        Args:
            user: The authenticated user
            income_transaction: The income transaction to split
            rule_ids: List of rule IDs to apply

        Returns:
            List of created expense transactions
        """
        if not rule_ids:
            return []

        # Fetch the selected rules
        result = await self.db.execute(
            select(IncomeSplitRule).where(
                IncomeSplitRule.id.in_(rule_ids),
                IncomeSplitRule.user_id == user.id,
                IncomeSplitRule.is_active == True,
            )
        )
        rules = list(result.scalars().all())

        created_expenses = []
        income_amount = float(income_transaction.amount)

        for rule in rules:
            # Calculate split amount
            split_amount = rule.calculate_split_amount(income_amount)

            if split_amount <= 0:
                continue

            # Format description
            description = rule.format_description(income_transaction.description)

            # Create expense transaction (already paid - money is committed)
            expense = Transaction(
                user_id=user.id,
                account_id=income_transaction.account_id,
                category_id=rule.category_id,
                type=TransactionType.EXPENSE.value,
                amount=split_amount,
                date=income_transaction.date,
                description=description,
                is_paid=True,  # Already paid - money is committed from income
                source_transaction_id=income_transaction.id,
                ownership_type=income_transaction.ownership_type,
            )
            self.db.add(expense)
            created_expenses.append(expense)

        await self.db.flush()
        return created_expenses

    async def get_splits_for_transaction(
        self, user: User, transaction_id: int
    ) -> list[Transaction]:
        """
        Get all split expenses generated from an income transaction.

        Args:
            user: The authenticated user
            transaction_id: ID of the source income transaction

        Returns:
            List of expense transactions generated from the income
        """
        result = await self.db.execute(
            select(Transaction).where(
                Transaction.source_transaction_id == transaction_id,
                Transaction.user_id == user.id,
            )
        )
        return list(result.scalars().all())

    async def get_rules_with_category_names(
        self, user: User, active_only: bool = True
    ) -> list[dict]:
        """
        Get all rules with their category names resolved.

        Args:
            user: The authenticated user
            active_only: If True, only return active rules

        Returns:
            List of rules as dicts with category_name included
        """
        rules = await self.list_rules(user, active_only)

        # Collect category IDs
        category_ids = [r.category_id for r in rules if r.category_id]
        category_names = {}

        if category_ids:
            cat_result = await self.db.execute(
                select(Category.id, Category.name).where(Category.id.in_(category_ids))
            )
            category_names = {row[0]: row[1] for row in cat_result.all()}

        result = []
        for rule in rules:
            result.append(
                IncomeSplitRuleResponse(
                    id=rule.id,
                    user_id=rule.user_id,
                    name=rule.name,
                    split_type=rule.split_type,
                    percentage=float(rule.percentage) if rule.percentage else None,
                    fixed_amount=float(rule.fixed_amount) if rule.fixed_amount else None,
                    category_id=rule.category_id,
                    category_name=category_names.get(rule.category_id),
                    description_template=rule.description_template,
                    is_active=rule.is_active,
                    priority=rule.priority,
                    created_at=rule.created_at,
                    updated_at=rule.updated_at,
                )
            )

        return result
