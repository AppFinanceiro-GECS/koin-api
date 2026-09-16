"""
Automation Service for financial automations.

Handles CRUD operations for automation rules and their execution.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models import (
    Account,
    ActionType,
    AutomationExecution,
    AutomationRule,
    Transaction,
    TriggerType,
    User,
)
from app.models.notification import NotificationPriority, NotificationType
from app.modules.automations.schemas import (
    AutomationExecutionResponse,
    AutomationRuleCreate,
    AutomationRuleListResponse,
    AutomationRuleResponse,
    AutomationRuleUpdate,
    AutomationTestResult,
)
from app.modules.notifications.services import NotificationService

logger = logging.getLogger(__name__)


class AutomationService:
    """Service for managing automation rules."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ==================== CRUD Operations ====================

    async def create(self, user: User, data: AutomationRuleCreate) -> AutomationRule:
        """Create a new automation rule."""
        rule = AutomationRule(
            user_id=user.id,
            name=data.name,
            description=data.description,
            trigger_type=data.trigger_type.value,
            trigger_config=data.trigger_config,
            conditions=data.conditions,
            action_type=data.action_type.value,
            action_config=data.action_config,
            is_active=data.is_active,
            priority=data.priority,
        )

        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)

        logger.info(f"Created automation rule {rule.id} for user {user.id}")
        return rule

    async def get(self, user: User, rule_id: int) -> AutomationRule | None:
        """Get an automation rule by ID."""
        result = await self.session.execute(
            select(AutomationRule).where(
                AutomationRule.id == rule_id, AutomationRule.user_id == user.id
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        user: User,
        include_inactive: bool = False,
        trigger_type: TriggerType | None = None,
        action_type: ActionType | None = None,
    ) -> AutomationRuleListResponse:
        """List automation rules for a user."""
        query = select(AutomationRule).where(AutomationRule.user_id == user.id)

        if not include_inactive:
            query = query.where(AutomationRule.is_active == True)

        if trigger_type:
            query = query.where(AutomationRule.trigger_type == trigger_type.value)

        if action_type:
            query = query.where(AutomationRule.action_type == action_type.value)

        query = query.order_by(AutomationRule.priority.desc(), AutomationRule.created_at.desc())

        result = await self.session.execute(query)
        rules = list(result.scalars().all())

        # Count totals
        total_result = await self.session.execute(
            select(func.count(AutomationRule.id)).where(AutomationRule.user_id == user.id)
        )
        total = total_result.scalar() or 0

        active_result = await self.session.execute(
            select(func.count(AutomationRule.id)).where(
                AutomationRule.user_id == user.id, AutomationRule.is_active == True
            )
        )
        active_count = active_result.scalar() or 0

        return AutomationRuleListResponse(
            rules=[self._to_response(r) for r in rules],
            total=total,
            active_count=active_count,
            disabled_count=total - active_count,
        )

    async def update(
        self, user: User, rule_id: int, data: AutomationRuleUpdate
    ) -> AutomationRule | None:
        """Update an automation rule."""
        rule = await self.get(user, rule_id)
        if not rule:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "trigger_type" and value:
                value = value.value
            elif key == "action_type" and value:
                value = value.value
            setattr(rule, key, value)

        # Reset error state if re-enabled
        if data.is_active and rule.auto_disabled_at:
            rule.auto_disabled_at = None
            rule.consecutive_failures = 0
            rule.last_error = None

        rule.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(rule)

        logger.info(f"Updated automation rule {rule_id}")
        return rule

    async def delete(self, user: User, rule_id: int) -> bool:
        """Delete an automation rule."""
        rule = await self.get(user, rule_id)
        if not rule:
            return False

        await self.session.delete(rule)
        await self.session.commit()

        logger.info(f"Deleted automation rule {rule_id}")
        return True

    async def toggle(self, user: User, rule_id: int) -> AutomationRule | None:
        """Toggle an automation rule active/inactive."""
        rule = await self.get(user, rule_id)
        if not rule:
            return None

        rule.is_active = not rule.is_active

        # Reset error state if re-enabling
        if rule.is_active:
            rule.auto_disabled_at = None
            rule.consecutive_failures = 0
            rule.last_error = None

        rule.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(rule)

        return rule

    # ==================== Execution ====================

    async def execute_rule(
        self, rule: AutomationRule, trigger_reason: str, context: dict | None = None
    ) -> AutomationExecution:
        """Execute an automation rule."""
        start_time = utc_now()
        execution = AutomationExecution(
            rule_id=rule.id,
            trigger_reason=trigger_reason,
            status="running",
        )
        self.session.add(execution)

        try:
            # Check conditions
            conditions_met, conditions_result = await self._evaluate_conditions(rule, context)
            execution.conditions_met = conditions_met
            execution.conditions_result = conditions_result

            if not conditions_met:
                execution.status = "skipped"
                execution.result_data = {"reason": "conditions_not_met"}
            else:
                # Execute action
                result = await self._execute_action(rule, context)
                execution.status = "success"
                execution.result_data = result

                # Update rule stats
                rule.last_executed_at = utc_now()
                rule.execution_count += 1
                rule.consecutive_failures = 0
                rule.last_error = None

        except Exception as e:
            logger.exception(f"Error executing rule {rule.id}: {e}")
            execution.status = "failed"
            execution.error_message = str(e)
            execution.error_details = {"type": type(e).__name__}

            # Update failure tracking
            rule.consecutive_failures += 1
            rule.last_error = str(e)

            # Auto-disable if too many failures
            if rule.consecutive_failures >= rule.max_consecutive_failures:
                rule.is_active = False
                rule.auto_disabled_at = utc_now()
                logger.warning(
                    f"Auto-disabled rule {rule.id} after {rule.consecutive_failures} failures"
                )

                # Notify user about auto-disabled automation
                try:
                    notification_service = NotificationService(self.session)
                    await notification_service.send_notification(
                        user_id=rule.user_id,
                        notification_type=NotificationType.AUTOMATION_DISABLED,
                        title=f"Automação '{rule.name}' desabilitada",
                        message=(
                            f"A automação foi desabilitada após {rule.consecutive_failures} "
                            f"falhas consecutivas. Verifique as condições e reative quando corrigido."
                        ),
                        entity_type="automation_rule",
                        entity_id=rule.id,
                        priority=NotificationPriority.HIGH,
                    )
                except Exception as notif_err:
                    logger.error(
                        f"Failed to send auto-disable notification for rule {rule.id}: {notif_err}"
                    )

        finally:
            end_time = utc_now()
            execution.duration_ms = int((end_time - start_time).total_seconds() * 1000)

        await self.session.commit()
        await self.session.refresh(execution)

        return execution

    async def _evaluate_conditions(
        self, rule: AutomationRule, context: dict | None = None
    ) -> tuple[bool, dict]:
        """Evaluate rule conditions."""
        conditions = rule.conditions
        if not conditions or not conditions.get("rules"):
            return True, {"evaluated": [], "result": "no_conditions"}

        rules = conditions.get("rules", [])
        match_type = conditions.get("match", "all")
        results = []

        for condition in rules:
            met = await self._evaluate_single_condition(rule.user_id, condition, context)
            results.append({"condition": condition, "met": met})

        if match_type == "all":
            all_met = all(r["met"] for r in results)
        else:
            all_met = any(r["met"] for r in results)

        return all_met, {"evaluated": results, "match_type": match_type, "result": all_met}

    async def _evaluate_single_condition(
        self, user_id: int, condition: dict, context: dict | None = None
    ) -> bool:
        """Evaluate a single condition."""
        cond_type = condition.get("type")

        if cond_type == "balance_above":
            account_id = condition.get("account_id")
            value = Decimal(str(condition.get("value", 0)))
            balance = await self._get_account_balance(user_id, account_id)
            return balance > value

        elif cond_type == "balance_below":
            account_id = condition.get("account_id")
            value = Decimal(str(condition.get("value", 0)))
            balance = await self._get_account_balance(user_id, account_id)
            return balance < value

        elif cond_type == "day_of_month":
            operator = condition.get("operator", "==")
            value = int(condition.get("value", 1))
            today = date.today().day
            return self._compare(today, operator, value)

        elif cond_type == "day_of_week":
            operator = condition.get("operator", "==")
            value = int(condition.get("value", 0))
            today = date.today().weekday()
            return self._compare(today, operator, value)

        # Default: condition met
        return True

    def _compare(self, left: Any, operator: str, right: Any) -> bool:
        """Compare two values with an operator."""
        if operator == "==":
            return left == right
        elif operator == "!=":
            return left != right
        elif operator == "<":
            return left < right
        elif operator == "<=":
            return left <= right
        elif operator == ">":
            return left > right
        elif operator == ">=":
            return left >= right
        return False

    async def _get_account_balance(self, user_id: int, account_id: int | None) -> Decimal:
        """Get account balance."""
        if account_id:
            result = await self.session.execute(
                select(Account.balance).where(Account.id == account_id, Account.user_id == user_id)
            )
            balance = result.scalar_one_or_none()
            return balance or Decimal(0)
        else:
            # Sum all account balances
            result = await self.session.execute(
                select(func.sum(Account.balance)).where(Account.user_id == user_id)
            )
            total = result.scalar()
            return total or Decimal(0)

    async def _execute_action(self, rule: AutomationRule, context: dict | None = None) -> dict:
        """Execute the rule's action."""
        action_type = rule.action_type
        config = rule.action_config

        if action_type == ActionType.TRANSFER.value:
            return await self._action_transfer(rule.user_id, config)
        elif action_type == ActionType.CATEGORIZE.value:
            return await self._action_categorize(rule.user_id, config, context)
        elif action_type == ActionType.NOTIFY.value:
            return await self._action_notify(rule.user_id, config)
        elif action_type == ActionType.TAG.value:
            return await self._action_tag(rule.user_id, config, context)
        elif action_type == ActionType.GENERATE.value:
            return await self._action_generate(rule.user_id, config)

        return {"action": action_type, "status": "unknown_action"}

    async def _action_transfer(self, user_id: int, config: dict) -> dict:
        """Execute a transfer action."""
        from_account_id = config.get("from_account_id")
        to_account_id = config.get("to_account_id")
        amount_type = config.get("amount_type", "fixed")
        amount_value = Decimal(str(config.get("amount_value", 0)))
        description = config.get("description", "Transferência automática")

        # Get accounts
        from_result = await self.session.execute(
            select(Account).where(Account.id == from_account_id, Account.user_id == user_id)
        )
        from_account = from_result.scalar_one_or_none()

        to_result = await self.session.execute(
            select(Account).where(Account.id == to_account_id, Account.user_id == user_id)
        )
        to_account = to_result.scalar_one_or_none()

        if not from_account or not to_account:
            raise ValueError("Invalid account(s) for transfer")

        # Calculate amount
        if amount_type == "fixed":
            amount = amount_value
        elif amount_type == "percentage":
            amount = from_account.balance * (amount_value / 100)
        elif amount_type == "remaining":
            # Transfer everything above a threshold
            threshold = amount_value or Decimal(0)
            amount = max(Decimal(0), from_account.balance - threshold)
        else:
            amount = amount_value

        if amount <= 0:
            return {
                "action": "transfer",
                "status": "skipped",
                "reason": "zero_or_negative_amount",
            }

        # Create transfer transactions
        now = utc_now()
        today = date.today()

        # Expense from source account
        expense = Transaction(
            user_id=user_id,
            account_id=from_account_id,
            amount=amount,
            type="expense",
            description=f"Transferência para {to_account.name}: {description}",
            date=today,
            is_transfer=True,
            transfer_account_id=to_account_id,
            created_at=now,
        )
        self.session.add(expense)

        # Income to destination account
        income = Transaction(
            user_id=user_id,
            account_id=to_account_id,
            amount=amount,
            type="income",
            description=f"Transferência de {from_account.name}: {description}",
            date=today,
            is_transfer=True,
            transfer_account_id=from_account_id,
            created_at=now,
        )
        self.session.add(income)

        # Update balances
        from_account.balance -= amount
        to_account.balance += amount

        await self.session.flush()

        return {
            "action": "transfer",
            "status": "success",
            "amount": float(amount),
            "from_account": from_account.name,
            "to_account": to_account.name,
            "expense_transaction_id": expense.id,
            "income_transaction_id": income.id,
        }

    async def _action_categorize(self, user_id: int, config: dict, context: dict | None) -> dict:
        """Execute a categorization action."""
        category_id = config.get("category_id")
        transaction_id = context.get("transaction_id") if context else None

        if not transaction_id:
            return {"action": "categorize", "status": "skipped", "reason": "no_transaction"}

        result = await self.session.execute(
            select(Transaction).where(
                Transaction.id == transaction_id, Transaction.user_id == user_id
            )
        )
        transaction = result.scalar_one_or_none()

        if not transaction:
            return {"action": "categorize", "status": "skipped", "reason": "transaction_not_found"}

        old_category_id = transaction.category_id
        transaction.category_id = category_id

        return {
            "action": "categorize",
            "status": "success",
            "transaction_id": transaction_id,
            "old_category_id": old_category_id,
            "new_category_id": category_id,
        }

    async def _action_notify(self, user_id: int, config: dict) -> dict:
        """Execute a notification action."""
        title = config.get("title", "Automação executada")
        message = config.get("message", "Uma automação foi executada")
        channels = config.get("channels", ["in_app"])

        # Get user
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {"action": "notify", "status": "skipped", "reason": "user_not_found"}

        # Create notification
        notification_service = NotificationService(self.session)
        notification = await notification_service.create_notification(
            user=user,
            type="automation_executed",
            title=title,
            message=message,
            priority="normal",
        )

        return {
            "action": "notify",
            "status": "success",
            "notification_id": notification.id,
            "channels": channels,
        }

    async def _action_tag(self, user_id: int, config: dict, context: dict | None) -> dict:
        """Execute a tagging action (placeholder)."""
        # Tags feature not fully implemented yet
        return {
            "action": "tag",
            "status": "skipped",
            "reason": "tags_not_implemented",
        }

    async def _action_generate(self, user_id: int, config: dict) -> dict:
        """Execute a transaction generation action."""
        trans_type = config.get("type", "expense")
        amount = Decimal(str(config.get("amount", 0)))
        description = config.get("description", "Transação automática")
        category_id = config.get("category_id")
        account_id = config.get("account_id")

        if not account_id:
            return {"action": "generate", "status": "skipped", "reason": "no_account"}

        # Verify account exists
        result = await self.session.execute(
            select(Account).where(Account.id == account_id, Account.user_id == user_id)
        )
        account = result.scalar_one_or_none()

        if not account:
            return {"action": "generate", "status": "skipped", "reason": "account_not_found"}

        # Create transaction
        now = utc_now()
        today = date.today()

        transaction = Transaction(
            user_id=user_id,
            account_id=account_id,
            amount=amount,
            type=trans_type,
            description=description,
            category_id=category_id,
            date=today,
            created_at=now,
        )
        self.session.add(transaction)

        # Update account balance
        if trans_type == "income":
            account.balance += amount
        else:
            account.balance -= amount

        await self.session.flush()

        return {
            "action": "generate",
            "status": "success",
            "transaction_id": transaction.id,
            "type": trans_type,
            "amount": float(amount),
        }

    # ==================== History ====================

    async def get_executions(
        self,
        user: User,
        rule_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[AutomationExecutionResponse]:
        """Get execution history."""
        query = (
            select(AutomationExecution)
            .join(AutomationRule)
            .where(AutomationRule.user_id == user.id)
        )

        if rule_id:
            query = query.where(AutomationExecution.rule_id == rule_id)

        if status:
            query = query.where(AutomationExecution.status == status)

        query = query.order_by(AutomationExecution.executed_at.desc()).limit(limit)

        result = await self.session.execute(query)
        executions = result.scalars().all()

        return [AutomationExecutionResponse.model_validate(e) for e in executions]

    # ==================== Testing ====================

    async def test_rule(
        self,
        user: User,
        rule_id: int | None = None,
        data: AutomationRuleCreate | None = None,
    ) -> AutomationTestResult:
        """Test an automation rule without executing it."""
        if rule_id:
            rule = await self.get(user, rule_id)
            if not rule:
                raise ValueError("Rule not found")
        elif data:
            # Create temporary rule object for testing
            rule = AutomationRule(
                user_id=user.id,
                name=data.name,
                trigger_type=data.trigger_type.value,
                trigger_config=data.trigger_config,
                conditions=data.conditions,
                action_type=data.action_type.value,
                action_config=data.action_config,
            )
        else:
            raise ValueError("Either rule_id or data must be provided")

        # Evaluate conditions
        conditions_met, conditions_detail = await self._evaluate_conditions(rule, None)

        # Simulate action
        simulated_action = None
        warnings = []

        if rule.action_type == ActionType.TRANSFER.value:
            config = rule.action_config
            from_id = config.get("from_account_id")

            from_balance = await self._get_account_balance(user.id, from_id)
            amount_type = config.get("amount_type")
            amount_value = Decimal(str(config.get("amount_value", 0)))

            if amount_type == "fixed":
                amount = amount_value
            elif amount_type == "percentage":
                amount = from_balance * (amount_value / 100)
            else:
                amount = from_balance

            simulated_action = {
                "type": "transfer",
                "amount": float(amount),
                "from_balance": float(from_balance),
            }

            if amount > from_balance:
                warnings.append("Saldo insuficiente para a transferência")

        return AutomationTestResult(
            would_execute=conditions_met,
            conditions_met=conditions_met,
            conditions_detail=conditions_detail.get("evaluated", []),
            simulated_action=simulated_action,
            warnings=warnings,
        )

    # ==================== Helpers ====================

    def _to_response(self, rule: AutomationRule) -> AutomationRuleResponse:
        """Convert rule to response schema."""
        response = AutomationRuleResponse.model_validate(rule)

        # Add summaries
        response.trigger_summary = self._get_trigger_summary(rule)
        response.action_summary = self._get_action_summary(rule)

        return response

    def _get_trigger_summary(self, rule: AutomationRule) -> str:
        """Get human-readable trigger summary."""
        trigger_type = rule.trigger_type
        config = rule.trigger_config

        if trigger_type == TriggerType.SCHEDULE.value:
            freq = config.get("frequency", "")
            if freq == "daily":
                return f"Diariamente às {config.get('time', '08:00')}"
            elif freq == "weekly":
                days = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
                day = config.get("day_of_week", 0)
                return f"Toda {days[day]} às {config.get('time', '08:00')}"
            elif freq == "monthly":
                day = config.get("day_of_month", 1)
                return f"Todo dia {day} às {config.get('time', '08:00')}"

        elif trigger_type == TriggerType.EVENT.value:
            event = config.get("event_type", "")
            event_names = {
                "transaction_created": "Transação criada",
                "invoice_due": "Fatura vencendo",
                "salary_received": "Salário recebido",
            }
            return event_names.get(event, event)

        elif trigger_type == TriggerType.THRESHOLD.value:
            threshold = config.get("threshold_type", "")
            value = config.get("value", 0)
            if "below" in threshold:
                return f"Saldo abaixo de R$ {value}"
            elif "above" in threshold:
                return f"Saldo acima de R$ {value}"

        return trigger_type

    def _get_action_summary(self, rule: AutomationRule) -> str:
        """Get human-readable action summary."""
        action_type = rule.action_type
        config = rule.action_config

        if action_type == ActionType.TRANSFER.value:
            amount_type = config.get("amount_type", "fixed")
            amount = config.get("amount_value", 0)
            if amount_type == "fixed":
                return f"Transferir R$ {amount}"
            elif amount_type == "percentage":
                return f"Transferir {amount}%"
            else:
                return "Transferir saldo restante"

        elif action_type == ActionType.NOTIFY.value:
            return "Enviar notificação"

        elif action_type == ActionType.CATEGORIZE.value:
            return "Categorizar transação"

        elif action_type == ActionType.GENERATE.value:
            trans_type = config.get("type", "expense")
            amount = config.get("amount", 0)
            type_name = "receita" if trans_type == "income" else "despesa"
            return f"Criar {type_name} de R$ {amount}"

        return action_type


# Fix missing import
