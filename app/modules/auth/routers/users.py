"""
Rotas de usuario: perfil, alteracao de senha, exportacao e exclusao (LGPD).
"""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select

from app.core.deps import CurrentUser, DbSession, security
from app.core.security import get_password_hash, validate_password_or_raise, verify_password
from app.core.services.email_service import email_service
from app.core.services.push_service import is_expo_token
from app.core.utils import utc_now
from app.models.push_device import PushDevice
from app.models.refresh_token import RefreshToken
from app.modules.auth.schemas.auth import SessionResponse
from app.modules.auth.schemas.user import ChangePassword, UserResponse, UserUpdate
from app.modules.auth.services import session_service
from app.modules.auth.services.user_service import UserService

router = APIRouter()

BearerCredentials = Annotated[HTTPAuthorizationCredentials, Depends(security)]


class DeviceRegister(BaseModel):
    expo_push_token: str = Field(max_length=200)
    platform: Literal["ios", "android"]
    app_version: str | None = Field(None, max_length=30)

    @field_validator("expo_push_token")
    @classmethod
    def expo_format(cls, value: str) -> str:
        if not is_expo_token(value):
            raise ValueError("Token de push do Expo inválido (ExponentPushToken[...])")
        return value


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    app_version: str | None
    created_at: datetime
    last_seen_at: datetime


class DeleteAccountRequest(BaseModel):
    current_password: str


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: CurrentUser):
    """Retorna dados do usuário autenticado"""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza dados do usuário autenticado"""
    user_service = UserService(db)
    return await user_service.update(current_user, data)


@router.post("/me/change-password")
async def change_password(
    data: ChangePassword,
    current_user: CurrentUser,
    db: DbSession,
    credentials: BearerCredentials,
    background_tasks: BackgroundTasks,
):
    """Altera a senha do usuário autenticado e encerra as sessões dos outros aparelhos"""
    # Verificar senha atual
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual incorreta")

    validate_password_or_raise(data.new_password)
    current_user.hashed_password = get_password_hash(data.new_password)
    await session_service.revoke_all(
        db,
        current_user.id,
        keep_family_id=session_service.session_id_from_access_token(credentials.credentials),
    )
    await db.commit()

    # Enviar notificação de alteração de senha
    # depois da resposta: o SMTP não segura a requisição nem o event loop
    background_tasks.add_task(
        email_service.send_password_changed_notification, current_user.email, current_user.name
    )

    return {"message": "Senha alterada com sucesso"}


@router.get("/me/sessions", response_model=list[SessionResponse])
async def list_sessions(current_user: CurrentUser, db: DbSession, credentials: BearerCredentials):
    """Aparelhos conectados: uma sessão por login ainda ativo"""
    current = session_service.session_id_from_access_token(credentials.credentials)
    sessions = await session_service.active_sessions(db, current_user.id)
    return [SessionResponse(**s, current=s["id"] == current) for s in sessions]


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: str, current_user: CurrentUser, db: DbSession):
    """Encerra a sessão de um aparelho"""
    owned = await db.scalar(
        select(RefreshToken.jti)
        .where(RefreshToken.family_id == session_id, RefreshToken.user_id == current_user.id)
        .limit(1)
    )
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    await session_service.revoke_family(db, session_id)
    await db.commit()


@router.post("/me/devices", response_model=DeviceResponse)
async def register_device(data: DeviceRegister, current_user: CurrentUser, db: DbSession):
    """Registra o aparelho para push (#43). Chamar a cada abertura do app: atualiza a
    versão e o último acesso. Token já usado por outra conta passa para esta."""
    device = await db.scalar(
        select(PushDevice).where(PushDevice.expo_push_token == data.expo_push_token)
    )
    now = utc_now()
    if device is None:
        device = PushDevice(expo_push_token=data.expo_push_token, created_at=now)
        db.add(device)
    device.user_id = current_user.id
    device.platform = data.platform
    device.app_version = data.app_version
    device.last_seen_at = now
    await db.commit()
    await db.refresh(device)
    return device


@router.get("/me/devices", response_model=list[DeviceResponse])
async def list_devices(current_user: CurrentUser, db: DbSession):
    return (
        await db.execute(select(PushDevice).where(PushDevice.user_id == current_user.id))
    ).scalars()


@router.delete("/me/devices/{expo_push_token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(expo_push_token: str, current_user: CurrentUser, db: DbSession):
    """Para de mandar push para o aparelho (chamar no logout). Idempotente."""
    await db.execute(
        delete(PushDevice).where(
            PushDevice.expo_push_token == expo_push_token,
            PushDevice.user_id == current_user.id,
        )
    )
    await db.commit()


@router.get("/me/export", status_code=status.HTTP_200_OK)
async def export_my_data(
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Exporta todos os dados pessoais e financeiros do usuário logado (Conformidade LGPD - Art. 18).
    """
    user_service = UserService(db)
    return await user_service.export_user_data(current_user)


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_my_account(
    payload: DeleteAccountRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Solicita a exclusão da conta do usuário (Soft Delete imediato + Auditoria LGPD).
    Exige reautenticação com a senha atual.
    """
    user_service = UserService(db)
    return await user_service.delete_account(current_user, payload.current_password)
