"""
Rotas de usuario: perfil, alteracao de senha, exportacao e exclusao (LGPD).
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.deps import CurrentUser, DbSession
from app.core.security import get_password_hash, validate_password_or_raise, verify_password
from app.core.services.email_service import email_service
from app.modules.auth.schemas.user import ChangePassword, UserResponse, UserUpdate
from app.modules.auth.services.user_service import UserService

router = APIRouter()


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
):
    """Altera a senha do usuário autenticado"""
    # Verificar senha atual
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual incorreta")

    validate_password_or_raise(data.new_password)
    current_user.hashed_password = get_password_hash(data.new_password)
    await db.commit()

    # Enviar notificação de alteração de senha
    email_service.send_password_changed_notification(current_user.email, current_user.name)

    return {"message": "Senha alterada com sucesso"}


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