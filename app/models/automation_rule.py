"""
Automation Rule model for financial automations.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class TriggerType(str, Enum):
    """Types of triggers that can activate an automation."""

    SCHEDULE = "schedule"  # Run on a schedule (daily, weekly, monthly)
    EVENT = "event"  # React to events (transaction created, invoice due, etc.)
    THRESHOLD = "threshold"  # React to thresholds (balance below X, budget above Y%)


class ActionType(str, Enum):
    """Types of actions an automation can perform."""

    TRANSFER = "transfer"  # Transfer between accounts
    CATEGORIZE = "categorize"  # Auto-categorize transaction
    NOTIFY = "notify"  # Send notification
    TAG = "tag"  # Add tag to transaction
    GENERATE = "generate"  # Generate a transaction


class ScheduleFrequency(str, Enum):
    """Frequency options for scheduled automations."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class EventType(str, Enum):
    """Event types that can trigger automations."""

    TRANSACTION_CREATED = "transaction_created"
    TRANSACTION_UPDATED = "transaction_updated"
    INVOICE_CLOSED = "invoice_closed"
    INVOICE_DUE = "invoice_due"
    GOAL_ACHIEVED = "goal_achieved"
    SALARY_RECEIVED = "salary_received"
    BUDGET_EXCEEDED = "budget_exceeded"


class ThresholdType(str, Enum):
    """Threshold types for conditional automations."""

    BALANCE_BELOW = "balance_below"
    BALANCE_ABOVE = "balance_above"
    BUDGET_PERCENT_ABOVE = "budget_percent_above"
    REMAINING_DAYS_BELOW = "remaining_days_below"


class AutomationRule(Base):
    """
    Automation rules for financial operations.

    Users can create rules that automatically perform actions
    based on triggers (schedule, events, thresholds).
    """

    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    # Trigger configuration
    trigger_type: Mapped[str] = mapped_column(String(20))
    trigger_config: Mapped[dict] = mapped_column(JSON, default=dict)
    """
    trigger_config examples:

    Schedule:
    {
        "frequency": "monthly",
        "day_of_month": 5,
        "day_of_week": null,  # For weekly
        "time": "08:00"
    }

    Event:
    {
        "event_type": "transaction_created",
        "filters": {
            "category_id": 123,
            "amount_min": 100,
            "description_contains": "salário"
        }
    }

    Threshold:
    {
        "threshold_type": "balance_below",
        "account_id": 456,
        "value": 500,
        "check_frequency": "daily"
    }
    """

    # Conditions (additional filters)
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    """
    conditions example:
    {
        "rules": [
            {"type": "balance_above", "account_id": 1, "value": 500},
            {"type": "day_of_month", "operator": "<=", "value": 25}
        ],
        "match": "all"  # or "any"
    }
    """

    # Action configuration
    action_type: Mapped[str] = mapped_column(String(20))
    action_config: Mapped[dict] = mapped_column(JSON, default=dict)
    """
    action_config examples:

    Transfer:
    {
        "from_account_id": 1,
        "to_account_id": 2,
        "amount_type": "fixed",  # fixed, percentage, remaining
        "amount_value": 500,
        "description": "Transferência automática para reserva"
    }

    Categorize:
    {
        "category_id": 123,
        "apply_to": "matching_transactions"
    }

    Notify:
    {
        "notification_type": "custom",
        "title": "Automação executada",
        "message": "Transferência realizada com sucesso",
        "channels": ["in_app", "push"]
    }

    Tag:
    {
        "tags": ["automático", "reserva"],
        "apply_to": "created_transaction"
    }

    Generate:
    {
        "type": "expense",
        "amount": 100,
        "description": "Aporte mensal",
        "category_id": 123,
        "account_id": 456
    }
    """

    # Status
    is_active: Mapped[bool] = mapped_column(default=True)
    priority: Mapped[int] = mapped_column(default=0)  # Higher = executed first

    # Execution tracking
    last_executed_at: Mapped[datetime | None] = mapped_column(default=None)
    execution_count: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    consecutive_failures: Mapped[int] = mapped_column(default=0)

    # Auto-disable after too many failures
    max_consecutive_failures: Mapped[int] = mapped_column(default=3)
    auto_disabled_at: Mapped[datetime | None] = mapped_column(default=None)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    # Ownership
    ownership_type: Mapped[str] = mapped_column(String(20), default="user")

    # Relationships
    user = relationship("User", back_populates="automation_rules")
    executions = relationship(
        "AutomationExecution", back_populates="rule", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_automation_rules_user_active", "user_id", "is_active"),
        Index("ix_automation_rules_trigger_type", "trigger_type"),
    )

    def __repr__(self) -> str:
        return f"<AutomationRule {self.id}: {self.name}>"


class AutomationExecution(Base):
    """
    Execution history for automation rules.
    Tracks when rules run, their results, and any errors.
    """

    __tablename__ = "automation_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="CASCADE"), index=True
    )

    # Execution details
    executed_at: Mapped[datetime] = mapped_column(default=utc_now)
    trigger_reason: Mapped[str] = mapped_column(String(100))
    """
    What triggered this execution:
    - "schedule:monthly:day_5"
    - "event:transaction_created:123"
    - "threshold:balance_below:500"
    """

    # Result
    status: Mapped[str] = mapped_column(String(20))  # success, failed, skipped
    result_data: Mapped[dict | None] = mapped_column(JSON, default=None)
    """
    result_data example:
    {
        "action": "transfer",
        "amount": 500,
        "from_account": "Conta Corrente",
        "to_account": "Reserva",
        "transaction_id": 789
    }
    """

    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    error_details: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Conditions evaluated
    conditions_met: Mapped[bool | None] = mapped_column(default=None)
    conditions_result: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Timing
    duration_ms: Mapped[int | None] = mapped_column(default=None)

    # Relationships
    rule = relationship("AutomationRule", back_populates="executions")

    __table_args__ = (Index("ix_automation_executions_rule_date", "rule_id", "executed_at"),)

    def __repr__(self) -> str:
        return f"<AutomationExecution {self.id}: {self.status}>"
