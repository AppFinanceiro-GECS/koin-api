"""
Rotas de autenticacao: login, refresh, convites e reset de senha.
"""

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.email_address import NormalizedEmail, normalize_email
from app.core.rate_limit import limiter
from app.core.security import get_password_hash, validate_password_or_raise
from app.core.services.email_service import email_service
from app.core.utils import utc_now
from app.models import Invitation, InvitationStatus, License, User
from app.models.household import HouseholdMember, HouseholdRole
from app.modules.auth.schemas.auth import LoginRequest, Token
from app.modules.auth.schemas.invitation import InviteRegister, InviteValidation
from app.modules.auth.schemas.user import UserResponse
from app.modules.auth.services.auth_service import AuthService
from app.modules.auth.services.password_reset import (
    assign_reset_token,
    forgot_email_is_limited,
    user_by_reset_token,
)
from app.modules.auth.services.user_setup import setup_new_user

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    """Retorna informações do usuário autenticado"""
    return current_user


# Registro público desabilitado - apenas via convite
# @router.post("/register", response_model=UserResponse, status_code=201)
# async def register(user_data: UserCreate, db: DbSession):
#     """Registra um novo usuário"""
#     auth_service = AuthService(db)
#     user_service = UserService(db)
#     user = await auth_service.register(user_data)
#     await user_service.setup_initial_data(user)
#     return user


@router.post("/login", response_model=Token)
@limiter.limit("60/minute")  # flood grosseiro por IP; bloqueio real é por e-mail (AuthService)
async def login(request: Request, credentials: LoginRequest, db: DbSession):
    """Autentica usuário e retorna tokens"""
    auth_service = AuthService(db)
    return await auth_service.login(credentials.email, credentials.password)


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


@router.post("/forgot-password", status_code=202)
@limiter.limit("20/hour")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: DbSession,
    background_tasks: BackgroundTasks,
):
    """Sempre 202: não revela se o e-mail existe, se a conta está inativa ou se o envio falhou."""
    if forgot_email_is_limited(data.email):
        raise HTTPException(
            status_code=429,
            detail="Muitas solicitações de recuperação. Tente novamente mais tarde.",
        )

    user = await db.scalar(select(User).where(User.email == data.email))
    if user and user.is_active:
        raw_token = assign_reset_token(user)
        await db.commit()
        reset_url = f"{settings.frontend_url}/reset-password/{raw_token}"
        background_tasks.add_task(
            email_service.send_password_reset,
            user.email,
            reset_url,
            user.name,
        )

    return {
        "message": "Se o e-mail estiver cadastrado, enviaremos instruções para redefinir a senha."
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(db: DbSession, refresh_token: str = Body(..., embed=True)):
    """Renova o access token usando refresh token"""
    auth_service = AuthService(db)
    return await auth_service.refresh_token(refresh_token)


# ========== Invitation Registration ==========


@router.get("/invite/{token}", response_model=InviteValidation)
async def validate_invitation(token: str, db: DbSession):
    """Valida um token de convite"""
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Convite não encontrado")

    # Verificar se expirou
    if utc_now() > invitation.expires_at:
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.EXPIRED
            await db.commit()
        raise HTTPException(status_code=400, detail="Convite expirado")

    if invitation.status != InvitationStatus.PENDING:
        status_str = (
            invitation.status.value
            if hasattr(invitation.status, "value")
            else str(invitation.status)
        )
        raise HTTPException(status_code=400, detail=f"Convite {status_str}")

    # license.type pode ser string ou Enum dependendo de como foi salvo
    license_type = None
    if invitation.license:
        lt = invitation.license.type
        license_type = lt.value if hasattr(lt, "value") else str(lt)

    return InviteValidation(
        email=invitation.email,
        license_type=license_type,
        is_valid=invitation.is_valid,
    )


@router.post("/invite/{token}", response_model=Token)
@limiter.limit("3/minute")
async def register_via_invitation(
    request: Request, token: str, data: InviteRegister, db: DbSession
):
    """Registra usuario via convite e cria HouseholdMember"""
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    # Verificar validade
    if utc_now() > invitation.expires_at:
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.EXPIRED
            await db.commit()
        raise HTTPException(status_code=400, detail="Convite expirado")

    if invitation.status != InvitationStatus.PENDING:
        status_str = (
            invitation.status.value
            if hasattr(invitation.status, "value")
            else str(invitation.status)
        )
        raise HTTPException(status_code=400, detail=f"Convite {status_str}")

    account_email = normalize_email(invitation.email)

    # Verificar se email ja existe
    existing = await db.scalar(select(User).where(User.email == account_email))
    if existing:
        raise HTTPException(status_code=400, detail="Email ja cadastrado")

    # Validar força da senha
    validate_password_or_raise(data.password)

    # Criar usuario
    user = User(
        email=account_email,
        hashed_password=get_password_hash(data.password),
        name=data.name,
        is_verified=True,  # Usuario via convite ja eh verificado
        license_id=invitation.license_id,
    )

    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Setup inicial (contas, categorias)
    await setup_new_user(db, user.id)

    # Criar HouseholdMember se tiver licenca
    if invitation.license_id:
        # Verificar se eh o primeiro membro da licenca
        existing_members = await db.scalar(
            select(func.count(HouseholdMember.id)).where(
                HouseholdMember.license_id == invitation.license_id
            )
        )

        is_first_member = (existing_members or 0) == 0

        # Criar HouseholdMember
        household_member = HouseholdMember(
            license_id=invitation.license_id,
            user_id=user.id,
            role=HouseholdRole.OWNER.value if is_first_member else HouseholdRole.MEMBER.value,
            invited_by_id=invitation.invited_by_id,
            can_invite_members=is_first_member,
            can_see_all=is_first_member,
        )
        db.add(household_member)

        # Se eh o primeiro membro, atualizar owner_user_id na licenca
        if is_first_member:
            license_result = await db.execute(
                select(License).where(License.id == invitation.license_id)
            )
            license = license_result.scalar_one_or_none()
            if license:
                license.owner_user_id = user.id

    # Marcar convite como aceito
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = utc_now()

    await db.commit()

    # Gerar tokens
    auth_service = AuthService(db)
    return await auth_service.login(account_email, data.password)


# ========== Password Reset ==========


class ResetPasswordValidation(BaseModel):
    email: str
    is_valid: bool


class ResetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=8, max_length=72)


async def _user_for_reset(token: str, db: DbSession) -> User:
    user = await user_by_reset_token(db, token)
    if not user:
        raise HTTPException(status_code=404, detail="Token inválido ou expirado")

    if user.reset_token_expires and utc_now() > user.reset_token_expires:
        user.reset_token = None
        user.reset_token_expires = None
        await db.commit()
        raise HTTPException(status_code=400, detail="Token expirado")

    return user


@router.get("/reset-password/{token}")
async def validate_reset_token(token: str, db: DbSession):
    """Valida um token de reset de senha"""
    user = await _user_for_reset(token, db)
    return {"email": user.email, "is_valid": True}


@router.post("/reset-password/{token}", response_model=Token)
@limiter.limit("3/minute")
async def reset_password(request: Request, token: str, data: ResetPasswordRequest, db: DbSession):
    """Redefine a senha usando o token"""
    user = await _user_for_reset(token, db)

    validate_password_or_raise(data.password)

    user_email = user.email
    user_name = user.name

    user.hashed_password = get_password_hash(data.password)
    user.reset_token = None
    user.reset_token_expires = None

    await db.commit()

    # Enviar notificação de alteração de senha
    email_service.send_password_changed_notification(user_email, user_name)

    # Fazer login automático
    auth_service = AuthService(db)
    return await auth_service.login(user_email, data.password)
