"""
Router for Financial Automations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import ActionType, TriggerType, User
from app.modules.automations.schemas import (
    AutomationExecutionResponse,
    AutomationRuleCreate,
    AutomationRuleListResponse,
    AutomationRuleResponse,
    AutomationRuleUpdate,
    AutomationTestResult,
)
from app.modules.automations.services import AutomationService

router = APIRouter(prefix="/automations", tags=["automations"])


@router.post("", response_model=AutomationRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_automation(
    data: AutomationRuleCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new automation rule."""
    service = AutomationService(session)
    rule = await service.create(current_user, data)
    return service._to_response(rule)


@router.get("", response_model=AutomationRuleListResponse)
async def list_automations(
    include_inactive: bool = False,
    trigger_type: TriggerType | None = None,
    action_type: ActionType | None = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List automation rules."""
    service = AutomationService(session)
    return await service.list(
        current_user,
        include_inactive=include_inactive,
        trigger_type=trigger_type,
        action_type=action_type,
    )


@router.get("/executions", response_model=list[AutomationExecutionResponse])
async def list_executions(
    rule_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get automation execution history."""
    service = AutomationService(session)
    return await service.get_executions(
        current_user,
        rule_id=rule_id,
        status=status,
        limit=limit,
    )


@router.get("/{rule_id}", response_model=AutomationRuleResponse)
async def get_automation(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get an automation rule by ID."""
    service = AutomationService(session)
    rule = await service.get(current_user, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found"
        )
    return service._to_response(rule)


@router.patch("/{rule_id}", response_model=AutomationRuleResponse)
async def update_automation(
    rule_id: int,
    data: AutomationRuleUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an automation rule."""
    service = AutomationService(session)
    rule = await service.update(current_user, rule_id, data)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found"
        )
    return service._to_response(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an automation rule."""
    service = AutomationService(session)
    deleted = await service.delete(current_user, rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found"
        )


@router.post("/{rule_id}/toggle", response_model=AutomationRuleResponse)
async def toggle_automation(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle an automation rule active/inactive."""
    service = AutomationService(session)
    rule = await service.toggle(current_user, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found"
        )
    return service._to_response(rule)


@router.post("/{rule_id}/test", response_model=AutomationTestResult)
async def test_automation(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test an automation rule without executing it."""
    service = AutomationService(session)
    try:
        return await service.test_rule(current_user, rule_id=rule_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{rule_id}/execute", response_model=AutomationExecutionResponse)
async def execute_automation(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually execute an automation rule."""
    service = AutomationService(session)
    rule = await service.get(current_user, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found"
        )

    execution = await service.execute_rule(
        rule,
        trigger_reason="manual_execution",
    )
    return AutomationExecutionResponse.model_validate(execution)


@router.get("/{rule_id}/executions", response_model=list[AutomationExecutionResponse])
async def get_rule_executions(
    rule_id: int,
    limit: int = 20,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get execution history for a specific rule."""
    service = AutomationService(session)

    # Verify rule exists and belongs to user
    rule = await service.get(current_user, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Automation rule not found"
        )

    return await service.get_executions(
        current_user,
        rule_id=rule_id,
        limit=limit,
    )
