import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import get_password_hash
from app.core.services.email_service import email_service
from app.core.utils import utc_now
from app.models import Invitation, InvitationStatus, License, LicenseStatus, User
from app.models.household import HouseholdMember, HouseholdRole
from app.modules.admin.schemas.admin import (
    AdminDashboard,
    HouseholdMemberSummary,
    LicenseCreate,
    LicenseResponse,
    LicenseUpdate,
    UserAdminCreate,
    UserAdminResponse,
    UserAdminUpdate,
    UserListResponse,
)
from app.modules.auth.schemas.invitation import InvitationCreate, InvitationListResponse
from app.modules.auth.services.user_setup import setup_new_user

router = APIRouter()

# Constantes de seguranca
RESET_TOKEN_EXPIRE_HOURS = 1


def require_admin(user: User):
    """Verifica se o usuario e admin"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Apenas administradores podem acessar.",
        )


# ========== Dashboard ==========


@router.get("/dashboard", response_model=AdminDashboard)
async def get_dashboard(current_user: CurrentUser, db: DbSession):
    """Dashboard com estatisticas gerais"""
    require_admin(current_user)

    # Count users
    total_users = await db.scalar(select(func.count(User.id)))
    active_users = await db.scalar(select(func.count(User.id)).where(User.is_active == True))
    admin_users = await db.scalar(select(func.count(User.id)).where(User.is_admin == True))

    # Count licenses
    total_licenses = await db.scalar(select(func.count(License.id)))
    active_licenses = await db.scalar(
        select(func.count(License.id)).where(License.status == LicenseStatus.ACTIVE)
    )
    expired_licenses = await db.scalar(
        select(func.count(License.id)).where(License.status == LicenseStatus.EXPIRED)
    )

    return AdminDashboard(
        total_users=total_users or 0,
        active_users=active_users or 0,
        admin_users=admin_users or 0,
        total_licenses=total_licenses or 0,
        active_licenses=active_licenses or 0,
        expired_licenses=expired_licenses or 0,
    )


# ========== Licenses ==========


@router.get("/licenses", response_model=list[LicenseResponse])
async def list_licenses(current_user: CurrentUser, db: DbSession):
    """Lista todas as licencas"""
    require_admin(current_user)

    result = await db.execute(select(License).order_by(License.created_at.desc()))
    licenses = result.scalars().all()

    if not licenses:
        return []

    license_ids = [lic.id for lic in licenses]

    # Batch: contar usuarios por licenca
    user_counts_result = await db.execute(
        select(User.license_id, func.count(User.id).label("count"))
        .where(User.license_id.in_(license_ids))
        .group_by(User.license_id)
    )
    user_counts = {row[0]: row[1] for row in user_counts_result.all()}

    # Batch: buscar todos os membros de todas as licencas
    members_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.license_id.in_(license_ids))
    )
    all_members = members_result.scalars().all()

    # Batch: buscar todos os usuarios dos membros
    member_user_ids = [m.user_id for m in all_members if m.user_id]
    users_by_id = {}
    if member_user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(member_user_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    # Agrupar membros por licenca
    members_by_license: dict[int, list] = {lic_id: [] for lic_id in license_ids}
    for m in all_members:
        members_by_license[m.license_id].append(m)

    # Batch: buscar owners
    owner_ids = [lic.owner_user_id for lic in licenses if lic.owner_user_id]
    owners_by_id = {}
    if owner_ids:
        owners_result = await db.execute(select(User).where(User.id.in_(owner_ids)))
        owners_by_id = {u.id: u for u in owners_result.scalars().all()}

    response = []
    for lic in licenses:
        members = members_by_license.get(lic.id, [])
        members_summary = []
        for m in members:
            user = users_by_id.get(m.user_id)
            members_summary.append(
                HouseholdMemberSummary(
                    id=m.id,
                    user_id=m.user_id,
                    user_name=user.name if user else None,
                    user_email=user.email if user else None,
                    role=m.role,
                    joined_at=m.joined_at,
                )
            )

        # Nome do owner
        owner_name = None
        if lic.owner_user_id:
            owner = owners_by_id.get(lic.owner_user_id)
            owner_name = owner.name if owner else None

        resp = LicenseResponse(
            id=lic.id,
            key=lic.key,
            code=lic.code,
            type=lic.type,
            status=lic.status,
            max_users=lic.max_users,
            max_transactions_per_month=lic.max_transactions_per_month,
            max_documents_per_month=lic.max_documents_per_month,
            has_ai_assistant=lic.has_ai_assistant,
            has_insights=lic.has_insights,
            has_debt_strategies=lic.has_debt_strategies,
            has_goals=lic.has_goals,
            has_budget=lic.has_budget,
            start_date=lic.start_date,
            end_date=lic.end_date,
            notes=lic.notes,
            created_at=lic.created_at,
            updated_at=lic.updated_at,
            is_valid=lic.is_valid,
            days_remaining=lic.days_remaining,
            user_count=user_counts.get(lic.id, 0),
            owner_email=lic.owner_email,
            owner_user_id=lic.owner_user_id,
            owner_name=owner_name,
            member_count=len(members),
            members=members_summary,
        )
        response.append(resp)

    return response


@router.post("/licenses", response_model=LicenseResponse, status_code=status.HTTP_201_CREATED)
async def create_license(
    data: LicenseCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma nova licenca e envia convite automatico para o owner"""
    require_admin(current_user)

    # Verificar se o email do owner ja esta cadastrado
    existing_user = await db.scalar(select(User).where(User.email == data.owner_email))
    if existing_user:
        # Get current license info
        current_license = (
            await db.scalar(select(License).where(License.id == existing_user.license_id))
            if existing_user.license_id
            else None
        )

        # If force_transfer flag is set, proceed with transfer
        if data.force_transfer:
            # Remove user from current license/household
            if existing_user.license_id:
                # Remove household membership
                await db.execute(
                    select(HouseholdMember).where(HouseholdMember.user_id == existing_user.id)
                )
                existing_membership = await db.scalar(
                    select(HouseholdMember).where(HouseholdMember.user_id == existing_user.id)
                )
                if existing_membership:
                    await db.delete(existing_membership)

                # Clear license_id from user (will be set to new license below)
                existing_user.license_id = None
                await db.flush()
        else:
            # Return info about existing user for frontend modal
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Email do proprietario ja esta cadastrado no sistema",
                    "existing_user": {
                        "email": existing_user.email,
                        "user_id": existing_user.id,
                        "user_name": existing_user.name,
                        "current_license_id": current_license.id if current_license else None,
                        "current_license_code": current_license.code if current_license else None,
                        "current_license_owner_email": current_license.owner_email
                        if current_license
                        else None,
                    },
                },
            )

    # Verificar se ja existe convite pendente para este email
    existing_invite = await db.scalar(
        select(Invitation).where(
            Invitation.email == data.owner_email, Invitation.status == InvitationStatus.PENDING
        )
    )
    if existing_invite and not data.force_transfer:
        raise HTTPException(status_code=400, detail="Ja existe um convite pendente para este email")

    # Cancel any existing pending invites for this email if force_transfer
    if data.force_transfer and existing_invite:
        existing_invite.status = InvitationStatus.CANCELLED

    # Generate unique key
    key = secrets.token_urlsafe(32)

    license = License(
        key=key,
        type=data.type,
        max_users=data.max_users,
        max_transactions_per_month=data.max_transactions_per_month,
        max_documents_per_month=data.max_documents_per_month,
        has_ai_assistant=data.has_ai_assistant,
        has_insights=data.has_insights,
        has_debt_strategies=data.has_debt_strategies,
        has_goals=data.has_goals,
        has_budget=data.has_budget,
        start_date=data.start_date,
        end_date=data.end_date,
        notes=data.notes,
        owner_email=data.owner_email,  # Novo campo
    )

    db.add(license)
    await db.flush()
    await db.refresh(license)

    # If this is a transfer of an existing user, link them directly
    if data.force_transfer and existing_user:
        # Update user's license_id
        existing_user.license_id = license.id

        # Set owner_user_id on license
        license.owner_user_id = existing_user.id

        # Create household membership as owner
        membership = HouseholdMember(
            license_id=license.id,
            user_id=existing_user.id,
            role=HouseholdRole.OWNER.value,
            can_create_transactions=True,
            can_edit_shared=True,
            can_invite_members=True,
            can_see_all=True,
        )
        db.add(membership)
        await db.commit()
        await db.refresh(license)

        return LicenseResponse(
            id=license.id,
            key=license.key,
            code=license.code,
            type=license.type,
            status=license.status,
            max_users=license.max_users,
            max_transactions_per_month=license.max_transactions_per_month,
            max_documents_per_month=license.max_documents_per_month,
            has_ai_assistant=license.has_ai_assistant,
            has_insights=license.has_insights,
            has_debt_strategies=license.has_debt_strategies,
            has_goals=license.has_goals,
            has_budget=license.has_budget,
            start_date=license.start_date,
            end_date=license.end_date,
            notes=license.notes,
            created_at=license.created_at,
            updated_at=license.updated_at,
            is_valid=license.is_valid,
            days_remaining=license.days_remaining,
            user_count=1,
            owner_email=license.owner_email,
            owner_user_id=existing_user.id,
            owner_name=existing_user.name,
            member_count=1,
            members=[
                HouseholdMemberSummary(
                    id=membership.id,
                    user_id=existing_user.id,
                    user_name=existing_user.name,
                    user_email=existing_user.email,
                    role=membership.role,
                    joined_at=membership.joined_at,
                )
            ],
        )

    # Criar convite automatico para o owner (new user case)
    invitation = Invitation(
        email=data.owner_email,
        license_id=license.id,
        invited_by_id=current_user.id,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Enviar email de convite
    invite_url = f"{settings.frontend_url}/invite/{invitation.token}"
    email_sent = email_service.send_invitation(
        to_email=data.owner_email,
        invite_url=invite_url,
        inviter_name=current_user.name,
    )

    if not email_sent:
        print(f"Aviso: Email nao enviado para {data.owner_email}")

    return LicenseResponse(
        id=license.id,
        key=license.key,
        code=license.code,
        type=license.type,
        status=license.status,
        max_users=license.max_users,
        max_transactions_per_month=license.max_transactions_per_month,
        max_documents_per_month=license.max_documents_per_month,
        has_ai_assistant=license.has_ai_assistant,
        has_insights=license.has_insights,
        has_debt_strategies=license.has_debt_strategies,
        has_goals=license.has_goals,
        has_budget=license.has_budget,
        start_date=license.start_date,
        end_date=license.end_date,
        notes=license.notes,
        created_at=license.created_at,
        updated_at=license.updated_at,
        is_valid=license.is_valid,
        days_remaining=license.days_remaining,
        user_count=0,
        owner_email=license.owner_email,
        owner_user_id=None,
        owner_name=None,
        member_count=0,
        members=[],
    )


@router.patch("/licenses/{license_id}", response_model=LicenseResponse)
async def update_license(
    license_id: int,
    data: LicenseUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza uma licenca"""
    require_admin(current_user)

    result = await db.execute(select(License).where(License.id == license_id))
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(status_code=404, detail="Licenca nao encontrada")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(license, key, value)

    await db.commit()
    await db.refresh(license)

    user_count = await db.scalar(select(func.count(User.id)).where(User.license_id == license.id))

    # Buscar membros
    members_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.license_id == license.id)
    )
    members = members_result.scalars().all()

    # Batch: buscar usuarios dos membros + owner
    user_ids_to_fetch = [m.user_id for m in members if m.user_id]
    if license.owner_user_id:
        user_ids_to_fetch.append(license.owner_user_id)

    users_by_id = {}
    if user_ids_to_fetch:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids_to_fetch)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    members_summary = []
    for m in members:
        user = users_by_id.get(m.user_id)
        members_summary.append(
            HouseholdMemberSummary(
                id=m.id,
                user_id=m.user_id,
                user_name=user.name if user else None,
                user_email=user.email if user else None,
                role=m.role,
                joined_at=m.joined_at,
            )
        )

    owner_name = None
    if license.owner_user_id:
        owner = users_by_id.get(license.owner_user_id)
        owner_name = owner.name if owner else None

    return LicenseResponse(
        id=license.id,
        key=license.key,
        code=license.code,
        type=license.type,
        status=license.status,
        max_users=license.max_users,
        max_transactions_per_month=license.max_transactions_per_month,
        max_documents_per_month=license.max_documents_per_month,
        has_ai_assistant=license.has_ai_assistant,
        has_insights=license.has_insights,
        has_debt_strategies=license.has_debt_strategies,
        has_goals=license.has_goals,
        has_budget=license.has_budget,
        start_date=license.start_date,
        end_date=license.end_date,
        notes=license.notes,
        created_at=license.created_at,
        updated_at=license.updated_at,
        is_valid=license.is_valid,
        days_remaining=license.days_remaining,
        user_count=user_count or 0,
        owner_email=license.owner_email,
        owner_user_id=license.owner_user_id,
        owner_name=owner_name,
        member_count=len(members),
        members=members_summary,
    )


@router.delete("/licenses/{license_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_license(
    license_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Deleta uma licenca"""
    require_admin(current_user)

    result = await db.execute(select(License).where(License.id == license_id))
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(status_code=404, detail="Licenca nao encontrada")

    # Check if license has users
    user_count = await db.scalar(select(func.count(User.id)).where(User.license_id == license.id))
    if user_count > 0:
        raise HTTPException(
            status_code=400, detail=f"Nao e possivel deletar. {user_count} usuario(s) vinculado(s)."
        )

    # Delete related invitations first
    await db.execute(delete(Invitation).where(Invitation.license_id == license.id))

    await db.delete(license)
    await db.commit()


@router.post("/licenses/{license_id}/resend-invitation", status_code=status.HTTP_200_OK)
async def resend_license_invitation(
    license_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Reenvia o convite de uma licenca e reseta a expiracao"""
    require_admin(current_user)

    # Verificar se licenca existe
    result = await db.execute(select(License).where(License.id == license_id))
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(status_code=404, detail="Licenca nao encontrada")

    if not license.owner_email:
        raise HTTPException(status_code=400, detail="Licenca nao tem email de proprietario")

    # Verificar se ja existe usuario cadastrado
    if license.owner_user_id:
        raise HTTPException(status_code=400, detail="Proprietario ja cadastrado")

    # Buscar convite pendente/expirado para esta licenca
    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.license_id == license_id,
            Invitation.status.in_([InvitationStatus.PENDING, InvitationStatus.EXPIRED]),
        )
    )

    if not invitation:
        # Criar novo convite se nao existir
        invitation = Invitation(
            email=license.owner_email,
            license_id=license_id,
            invited_by_id=current_user.id,
        )
        db.add(invitation)
    else:
        # Reset expiracao
        invitation.expires_at = utc_now() + timedelta(hours=48)
        if invitation.status == InvitationStatus.EXPIRED:
            invitation.status = InvitationStatus.PENDING

    await db.commit()
    await db.refresh(invitation)

    # Enviar email
    invite_url = f"{settings.frontend_url}/invite/{invitation.token}"
    email_sent = email_service.send_invitation(
        to_email=invitation.email,
        invite_url=invite_url,
        inviter_name=current_user.name,
    )

    if not email_sent:
        raise HTTPException(status_code=500, detail="Falha ao enviar email")

    return {
        "message": "Convite reenviado com sucesso",
        "expires_at": invitation.expires_at.isoformat(),
    }


# ========== Users ==========


@router.get("/users", response_model=list[UserListResponse])
async def list_users(current_user: CurrentUser, db: DbSession):
    """Lista todos os usuarios"""
    require_admin(current_user)

    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return [UserListResponse.model_validate(u) for u in users]


@router.post("/users", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserAdminCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria um novo usuario. Se senha nao for informada, envia convite por email."""
    require_admin(current_user)

    # Check if email exists
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing:
        raise HTTPException(status_code=400, detail="Email ja cadastrado")

    # Validate license if provided
    license = None
    if data.license_id:
        license = await db.scalar(select(License).where(License.id == data.license_id))
        if not license:
            raise HTTPException(status_code=400, detail="Licenca nao encontrada")

    # If password provided, create user directly
    if data.password:
        user = User(
            email=data.email,
            hashed_password=get_password_hash(data.password),
            name=data.name,
            is_admin=data.is_admin,
            license_id=data.license_id,
            is_verified=True,
        )

        db.add(user)
        await db.flush()
        await db.refresh(user)

        # Create default accounts and categories
        await setup_new_user(db, user.id)

        await db.commit()

        return UserAdminResponse.model_validate(user)

    # No password - create invitation and send email
    existing_invite = await db.scalar(
        select(Invitation).where(
            Invitation.email == data.email, Invitation.status == InvitationStatus.PENDING
        )
    )
    if existing_invite:
        raise HTTPException(status_code=400, detail="Ja existe um convite pendente para este email")

    invitation = Invitation(
        email=data.email,
        license_id=data.license_id,
        invited_by_id=current_user.id,
    )

    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Send invitation email
    invite_url = f"{settings.frontend_url}/invite/{invitation.token}"
    email_sent = email_service.send_invitation(
        to_email=data.email,
        invite_url=invite_url,
        inviter_name=current_user.name,
    )

    if not email_sent:
        print(f"Aviso: Email nao enviado para {data.email}")

    # Return placeholder response (user will be created when invitation is accepted)
    return UserAdminResponse(
        id=0,
        email=data.email,
        name=data.name,
        is_active=False,
        is_verified=False,
        is_admin=data.is_admin,
        license_id=data.license_id,
        created_at=invitation.created_at,
        updated_at=invitation.created_at,
    )


@router.get("/users/{user_id}", response_model=UserAdminResponse)
async def get_user(
    user_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Obtem detalhes de um usuario"""
    require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    return UserAdminResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserAdminResponse)
async def update_user(
    user_id: int,
    data: UserAdminUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza um usuario"""
    require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    update_data = data.model_dump(exclude_unset=True)

    # Hash password if being updated
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
    elif "password" in update_data:
        del update_data["password"]

    # Check email uniqueness
    if "email" in update_data:
        existing = await db.scalar(
            select(User).where(User.email == update_data["email"], User.id != user_id)
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email ja cadastrado")

    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)

    return UserAdminResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Deleta um usuario"""
    require_admin(current_user)

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Nao e possivel deletar a si mesmo")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    await db.delete(user)
    await db.commit()


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_200_OK)
async def send_password_reset(
    user_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Envia email de redefinicao de senha para o usuario"""
    require_admin(current_user)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    # Gerar token de reset com expiracao
    reset_token = secrets.token_urlsafe(32)
    user.reset_token = reset_token
    user.reset_token_expires = utc_now() + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS)

    await db.commit()

    # Enviar email
    reset_url = f"{settings.frontend_url}/reset-password/{reset_token}"
    email_sent = email_service.send_password_reset(
        to_email=user.email,
        reset_url=reset_url,
        user_name=user.name,
    )

    if not email_sent:
        raise HTTPException(status_code=500, detail="Falha ao enviar email")

    return {"message": "Email de redefinicao de senha enviado com sucesso"}


# ========== Invitations ==========


@router.get("/invitations", response_model=list[InvitationListResponse])
async def list_invitations(current_user: CurrentUser, db: DbSession):
    """Lista todos os convites"""
    require_admin(current_user)

    result = await db.execute(select(Invitation).order_by(Invitation.created_at.desc()))
    invitations = result.scalars().all()

    if not invitations:
        return []

    # Batch: buscar licencas
    license_ids = [inv.license_id for inv in invitations if inv.license_id]
    licenses_by_id = {}
    if license_ids:
        lic_result = await db.execute(select(License).where(License.id.in_(license_ids)))
        licenses_by_id = {lic.id: lic for lic in lic_result.scalars().all()}

    # Batch: buscar usuarios que convidaram
    invited_by_ids = [inv.invited_by_id for inv in invitations if inv.invited_by_id]
    users_by_id = {}
    if invited_by_ids:
        users_result = await db.execute(select(User).where(User.id.in_(invited_by_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    response = []
    for inv in invitations:
        license = licenses_by_id.get(inv.license_id)
        invited_by = users_by_id.get(inv.invited_by_id)
        response.append(
            InvitationListResponse(
                id=inv.id,
                email=inv.email,
                status=inv.status,
                license_id=inv.license_id,
                license_code=license.code if license else None,
                invited_by_name=invited_by.name if invited_by else "Desconhecido",
                expires_at=inv.expires_at,
                created_at=inv.created_at,
            )
        )

    return response


@router.post(
    "/invitations", response_model=InvitationListResponse, status_code=status.HTTP_201_CREATED
)
async def create_invitation(
    data: InvitationCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria e envia um convite por email"""
    require_admin(current_user)

    # Verificar se email ja esta cadastrado
    existing_user = await db.scalar(select(User).where(User.email == data.email))
    if existing_user:
        raise HTTPException(status_code=400, detail="Email ja cadastrado no sistema")

    # Verificar se ja existe convite pendente
    existing_invite = await db.scalar(
        select(Invitation).where(
            Invitation.email == data.email, Invitation.status == InvitationStatus.PENDING
        )
    )
    if existing_invite:
        raise HTTPException(status_code=400, detail="Ja existe um convite pendente para este email")

    # Validar licenca se fornecida
    license = None
    if data.license_id:
        license = await db.scalar(select(License).where(License.id == data.license_id))
        if not license:
            raise HTTPException(status_code=400, detail="Licenca nao encontrada")

    # Criar convite
    invitation = Invitation(
        email=data.email,
        license_id=data.license_id,
        invited_by_id=current_user.id,
    )

    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # Enviar email
    invite_url = f"{settings.frontend_url}/invite/{invitation.token}"
    email_sent = email_service.send_invitation(
        to_email=data.email,
        invite_url=invite_url,
        inviter_name=current_user.name,
    )

    if not email_sent:
        # Log mas nao falha - convite foi criado
        print(f"Aviso: Email nao enviado para {data.email}")

    return InvitationListResponse(
        id=invitation.id,
        email=invitation.email,
        status=invitation.status,
        license_id=invitation.license_id,
        license_code=license.code if license else None,
        invited_by_name=current_user.name,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.post("/invitations/{invitation_id}/resend", status_code=status.HTTP_200_OK)
async def resend_invitation(
    invitation_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Reenvia email de convite e reseta a expiracao"""
    require_admin(current_user)

    result = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    if invitation.status == InvitationStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Convite ja foi aceito")

    if invitation.status == InvitationStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Convite foi cancelado")

    # Reset expiration to 48 hours from now
    invitation.expires_at = utc_now() + timedelta(hours=48)

    # If expired, set back to pending
    if invitation.status == InvitationStatus.EXPIRED:
        invitation.status = InvitationStatus.PENDING

    await db.commit()

    # Enviar email novamente
    invite_url = f"{settings.frontend_url}/invite/{invitation.token}"
    email_sent = email_service.send_invitation(
        to_email=invitation.email,
        invite_url=invite_url,
        inviter_name=invitation.invited_by.name if invitation.invited_by else "Administrador",
    )

    if not email_sent:
        raise HTTPException(status_code=500, detail="Falha ao enviar email")

    return {
        "message": "Email reenviado e expiracao resetada",
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    invitation_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cancela um convite"""
    require_admin(current_user)

    result = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    if invitation.status == InvitationStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Convite ja foi aceito")

    invitation.status = InvitationStatus.CANCELLED
    await db.commit()
