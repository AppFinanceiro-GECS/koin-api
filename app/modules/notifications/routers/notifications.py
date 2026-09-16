from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, DbSession
from app.models.notification import NotificationType
from app.modules.notifications.schemas.notification import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationPreferenceWithDefaults,
    NotificationResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    NotificationSummary,
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    UnreadCountResponse,
)
from app.modules.notifications.services.notification_service import NotificationService

router = APIRouter()


# === Notifications ===


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    notification_type: NotificationType | None = Query(None, alias="type"),
):
    """Lista notificações do usuário."""
    service = NotificationService(db)
    return await service.list_notifications(
        current_user,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
        notification_type=notification_type,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna contagem de notificações não lidas."""
    service = NotificationService(db)
    return await service.get_unread_count(current_user)


@router.get("/summary", response_model=NotificationSummary)
async def get_summary(
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna resumo das notificações."""
    service = NotificationService(db)
    return await service.get_summary(current_user)


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma notificação específica."""
    service = NotificationService(db)
    notification = await service.get_notification(current_user, notification_id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificação não encontrada",
        )
    return notification


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Marca uma notificação como lida."""
    service = NotificationService(db)
    notification = await service.mark_as_read(current_user, notification_id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificação não encontrada",
        )
    return notification


@router.post("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_as_read(
    current_user: CurrentUser,
    db: DbSession,
):
    """Marca todas as notificações como lidas."""
    service = NotificationService(db)
    count = await service.mark_all_as_read(current_user)
    return {"message": f"{count} notificações marcadas como lidas"}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_notification(
    notification_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Dispensa (oculta) uma notificação."""
    service = NotificationService(db)
    success = await service.dismiss_notification(current_user, notification_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificação não encontrada",
        )


# === Preferences ===


@router.get("/preferences", response_model=list[NotificationPreferenceWithDefaults])
async def list_preferences(
    current_user: CurrentUser,
    db: DbSession,
):
    """Lista todas as preferências de notificação."""
    service = NotificationService(db)
    return await service.list_preferences(current_user)


@router.get("/preferences/{notification_type}", response_model=NotificationPreferenceResponse)
async def get_preference(
    notification_type: NotificationType,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna preferência para um tipo de notificação."""
    service = NotificationService(db)
    preference = await service.get_preference(current_user, notification_type)
    if not preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preferência não encontrada. Use PUT para criar.",
        )
    return preference


@router.put("/preferences/{notification_type}", response_model=NotificationPreferenceResponse)
async def update_preference(
    notification_type: NotificationType,
    data: NotificationPreferenceUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza ou cria preferência para um tipo de notificação."""
    service = NotificationService(db)
    return await service.update_preference(current_user, notification_type, data)


# === Settings ===


@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_settings(
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna configurações globais de notificação."""
    service = NotificationService(db)
    return await service.get_settings(current_user)


@router.put("/settings", response_model=NotificationSettingsResponse)
async def update_settings(
    data: NotificationSettingsUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza configurações globais de notificação."""
    service = NotificationService(db)
    return await service.update_settings(current_user, data)


# === Push Subscriptions ===


@router.post("/push/subscribe", response_model=PushSubscriptionResponse)
async def subscribe_push(
    data: PushSubscriptionCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Inscreve dispositivo para receber push notifications."""
    service = NotificationService(db)
    return await service.subscribe_push(current_user, data)


@router.post("/push/unsubscribe", status_code=status.HTTP_200_OK)
async def unsubscribe_push(
    endpoint: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cancela inscrição de push notifications para um endpoint."""
    service = NotificationService(db)
    success = await service.unsubscribe_push(current_user, endpoint)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription não encontrada",
        )
    return {"message": "Inscrição cancelada com sucesso"}


@router.get("/push/subscriptions", response_model=list[PushSubscriptionResponse])
async def list_push_subscriptions(
    current_user: CurrentUser,
    db: DbSession,
):
    """Lista inscrições de push ativas."""
    service = NotificationService(db)
    return await service.list_push_subscriptions(current_user)
