"""
Rotas de usuario: perfil, alteracao de senha, exportacao e exclusao (LGPD).
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, security
from app.core.security import get_password_hash, validate_password_or_raise, verify_password
from app.core.services.email_service import email_service
from app.models.refresh_token import RefreshToken
from app.modules.auth.schemas.auth import SessionResponse
from app.modules.auth.schemas.user import ChangePassword, UserResponse, UserUpdate
from app.modules.auth.services import session_service
from app.modules.auth.services.user_service import UserService

router = APIRouter()

BearerCredentials = Annotated[HTTPAuthorizationCredentials, Depends(security)]


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
