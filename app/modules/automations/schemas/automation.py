"""
Schemas for Financial Automations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.automation_rule import (
    ActionType,
    EventType,
    ScheduleFrequency,
    ThresholdType,
    TriggerType,
)

# ==================== Trigger Configs ====================


class TriggerConfigSchedule(BaseModel):
    """Configuration for schedule-based triggers."""

    frequency: ScheduleFrequency
    day_of_month: int | None = Field(None, ge=1, le=31)
    day_of_week: int | None = Field(None, ge=0, le=6)  # 0=Monday, 6=Sunday
    time: str = "08:00"  # HH:MM format

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            parts = v.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time")
        except (ValueError, IndexError):
            raise ValueError("Time must be in HH:MM format")
        return v


class TriggerConfigEvent(BaseModel):
    """Configuration for event-based triggers."""

    event_type: EventType
    filters: dict = Field(default_factory=dict)
    """
    filters can include:
    - category_id: int
    - account_id: int
    - amount_min: Decimal
    - amount_max: Decimal
    - description_contains: str
    - is_income: bool
    """


class TriggerConfigThreshold(BaseModel):
    """Configuration for threshold-based triggers."""

    threshold_type: ThresholdType
    account_id: int | None = None
    category_id: int | None = None
    value: Decimal
    check_frequency: str = "daily"  # daily, hourly


# ==================== Action Configs ====================


class ActionConfigTransfer(BaseModel):
    """Configuration for transfer actions."""

    from_account_id: int
    to_account_id: int
    amount_type: Literal["fixed", "percentage", "remaining"]
    amount_value: Decimal | None = None  # Required for fixed/percentage
    description: str = "Transferência automática"


class ActionConfigCategorize(BaseModel):
    """Configuration for categorization actions."""

    category_id: int


class ActionConfigNotify(BaseModel):
    """Configuration for notification actions."""

    title: str
    message: str
    channels: list[str] = ["in_app"]  # in_app, push, email


class ActionConfigTag(BaseModel):
    """Configuration for tagging actions."""

    tags: list[str]


class ActionConfigGenerate(BaseModel):
    """Configuration for transaction generation actions."""

    type: Literal["income", "expense"]
    amount: Decimal
    description: str
    category_id: int | None = None
    account_id: int


# ==================== Conditions ====================


class ConditionRule(BaseModel):
    """A single condition rule."""

    type: str  # balance_above, balance_below, day_of_month, etc.
    account_id: int | None = None
    category_id: int | None = None
    operator: str | None = None  # <=, >=, ==, <, >
    value: Decimal | int | str | None = None


class ConditionsConfig(BaseModel):
    """Configuration for conditions."""

    rules: list[ConditionRule] = Field(default_factory=list)
    match: Literal["all", "any"] = "all"


# ==================== Request/Response Schemas ====================


class AutomationRuleCreate(BaseModel):
    """Schema for creating an automation rule."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None

    trigger_type: TriggerType
    trigger_config: dict = Field(default_factory=dict)

    conditions: dict = Field(default_factory=dict)

    action_type: ActionType
    action_config: dict = Field(default_factory=dict)

    is_active: bool = True
    priority: int = Field(0, ge=0, le=100)


class AutomationRuleUpdate(BaseModel):
    """Schema for updating an automation rule."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None

    trigger_type: TriggerType | None = None
    trigger_config: dict | None = None

    conditions: dict | None = None

    action_type: ActionType | None = None
    action_config: dict | None = None

    is_active: bool | None = None
    priority: int | None = Field(None, ge=0, le=100)


class AutomationRuleResponse(BaseModel):
    """Response schema for an automation rule."""

    id: int
    name: str
    description: str | None

    trigger_type: str
    trigger_config: dict

    conditions: dict

    action_type: str
    action_config: dict

    is_active: bool
    priority: int

    last_executed_at: datetime | None
    execution_count: int
    last_error: str | None
    consecutive_failures: int
    auto_disabled_at: datetime | None

    created_at: datetime
    updated_at: datetime

    # Computed fields
    trigger_summary: str | None = None
    action_summary: str | None = None
    next_execution: datetime | None = None

    model_config = {"from_attributes": True}


class AutomationRuleListResponse(BaseModel):
    """Response for listing automation rules."""

    rules: list[AutomationRuleResponse]
    total: int
    active_count: int
    disabled_count: int


class AutomationExecutionResponse(BaseModel):
    """Response schema for an automation execution."""

    id: int
    rule_id: int
    executed_at: datetime
    trigger_reason: str
    status: str
    result_data: dict | None
    error_message: str | None
    conditions_met: bool | None
    duration_ms: int | None

    model_config = {"from_attributes": True}


class AutomationTestResult(BaseModel):
    """Result of testing an automation rule."""

    would_execute: bool
    conditions_met: bool
    conditions_detail: list[dict]
    simulated_action: dict | None
    warnings: list[str]
