"""
Rotas de usuario: perfil e alteracao de senha.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser, DbSession
from app.core.security import get_password_hash, verify_password
from app.core.services.email_service import email_service
from app.modules.auth.schemas.user import ChangePassword, UserResponse, UserUpdate
from app.modules.auth.services.user_service import UserService

router = APIRouter()


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

    # Atualizar senha
    current_user.hashed_password = get_password_hash(data.new_password)
    await db.commit()

    # Enviar notificação de alteração de senha
    email_service.send_password_changed_notification(current_user.email, current_user.name)

    return {"message": "Senha alterada com sucesso"}
