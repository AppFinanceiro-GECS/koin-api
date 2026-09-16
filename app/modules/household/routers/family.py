"""
Rotas para gerenciamento de familia/household.
Permite ao owner convidar membros e gerenciar a familia.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.services.email_service import email_service
from app.models import Invitation, InvitationStatus, License, User
from app.models.household import HouseholdMember, HouseholdRole
from app.modules.household.schemas.household import (
    FamilyContext,
    FamilyInvitationResponse,
    FamilyInviteRequest,
    FamilyInviteResponse,
    HouseholdMemberResponse,
)

router = APIRouter()


def require_license(user: User):
    """Verifica se o usuario tem licenca"""
    if not user.license_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuario nao possui licenca"
        )


def require_can_invite(user: User):
    """Verifica se o usuario pode convidar membros"""
    if not user.household_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuario nao pertence a nenhuma familia"
        )
    if not user.household_membership.can_invite_members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissao para convidar membros"
        )


@router.get("/context", response_model=FamilyContext)
async def get_family_context(current_user: CurrentUser, db: DbSession):
    """Retorna contexto da familia do usuario logado"""
    require_license(current_user)

    # Buscar licenca
    license_result = await db.execute(select(License).where(License.id == current_user.license_id))
    license = license_result.scalar_one_or_none()

    if not license:
        raise HTTPException(status_code=404, detail="Licenca nao encontrada")

    # Buscar membros
    members_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.license_id == license.id)
    )
    members = members_result.scalars().all()

    # Batch: buscar usuarios dos membros
    user_ids = [m.user_id for m in members if m.user_id]
    users_by_id = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    members_response = []
    for m in members:
        user = users_by_id.get(m.user_id)
        members_response.append(
            HouseholdMemberResponse(
                id=m.id,
                license_id=m.license_id,
                user_id=m.user_id,
                user_name=user.name if user else None,
                user_email=user.email if user else None,
                role=m.role,
                nickname=m.nickname,
                joined_at=m.joined_at,
                invited_by_id=m.invited_by_id,
                can_create_transactions=m.can_create_transactions,
                can_edit_shared=m.can_edit_shared,
                can_invite_members=m.can_invite_members,
                can_see_all=m.can_see_all,
            )
        )

    # Verificar se usuario eh owner
    is_owner = False
    can_invite = False
    if current_user.household_membership:
        is_owner = current_user.household_membership.role == HouseholdRole.OWNER.value
        can_invite = current_user.household_membership.can_invite_members

    # Tipo da licenca
    license_type = license.type.value if hasattr(license.type, "value") else str(license.type)

    return FamilyContext(
        license_id=license.id,
        license_type=license_type,
        is_owner=is_owner,
        can_invite=can_invite,
        member_count=len(members),
        max_members=license.max_users,
        members=members_response,
    )


@router.get("/members", response_model=list[HouseholdMemberResponse])
async def list_members(current_user: CurrentUser, db: DbSession):
    """Lista membros da familia"""
    require_license(current_user)

    members_result = await db.execute(
        select(HouseholdMember).where(HouseholdMember.license_id == current_user.license_id)
    )
    members = members_result.scalars().all()

    if not members:
        return []

    # Batch: buscar usuarios dos membros
    user_ids = [m.user_id for m in members if m.user_id]
    users_by_id = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_by_id = {u.id: u for u in users_result.scalars().all()}

    response = []
    for m in members:
        user = users_by_id.get(m.user_id)
        response.append(
            HouseholdMemberResponse(
                id=m.id,
                license_id=m.license_id,
                user_id=m.user_id,
                user_name=user.name if user else None,
                user_email=user.email if user else None,
                role=m.role,
                nickname=m.nickname,
                joined_at=m.joined_at,
                invited_by_id=m.invited_by_id,
                can_create_transactions=m.can_create_transactions,
                can_edit_shared=m.can_edit_shared,
                can_invite_members=m.can_invite_members,
                can_see_all=m.can_see_all,
            )
        )

    return response


@router.post("/invite", response_model=FamilyInviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    data: FamilyInviteRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Owner convida novo membro para a familia"""
    require_license(current_user)
    require_can_invite(current_user)

    # Buscar licenca para verificar limite
    license_result = await db.execute(select(License).where(License.id == current_user.license_id))
    license = license_result.scalar_one_or_none()

    if not license:
        raise HTTPException(status_code=404, detail="Licenca nao encontrada")

    # Verificar limite de usuarios
    if not license.can_add_members:
        raise HTTPException(
            status_code=400, detail=f"Limite de {license.max_users} membros atingido"
        )

    # Verificar se email ja esta cadastrado no sistema
    existing_user = await db.scalar(select(User).where(User.email == data.email))
    if existing_user:
        # Verificar se ja eh membro desta familia
        existing_member = await db.scalar(
            select(HouseholdMember).where(
                HouseholdMember.license_id == license.id,
                HouseholdMember.user_id == existing_user.id,
            )
        )
        if existing_member:
            raise HTTPException(status_code=400, detail="Usuario ja eh membro desta familia")
        raise HTTPException(status_code=400, detail="Email ja cadastrado no sistema")

    # Verificar se ja existe convite pendente
    existing_invite = await db.scalar(
        select(Invitation).where(
            Invitation.email == data.email, Invitation.status == InvitationStatus.PENDING
        )
    )
    if existing_invite:
        raise HTTPException(status_code=400, detail="Ja existe um convite pendente para este email")

    # Criar convite
    invitation = Invitation(
        email=data.email,
        license_id=license.id,
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
        print(f"Aviso: Email nao enviado para {data.email}")

    # Status pode ser Enum ou string dependendo de como foi carregado
    status_value = (
        invitation.status.value if hasattr(invitation.status, "value") else str(invitation.status)
    )

    return FamilyInviteResponse(
        invitation_id=invitation.id,
        email=invitation.email,
        status=status_value,
        expires_at=invitation.expires_at,
    )


@router.get("/invitations", response_model=list[FamilyInvitationResponse])
async def list_family_invitations(current_user: CurrentUser, db: DbSession):
    """Lista convites pendentes da familia"""
    require_license(current_user)

    invitations_result = await db.execute(
        select(Invitation)
        .where(
            Invitation.license_id == current_user.license_id,
            Invitation.status == InvitationStatus.PENDING,
        )
        .order_by(Invitation.created_at.desc())
    )
    invitations = invitations_result.scalars().all()

    response = []
    for inv in invitations:
        status_value = inv.status.value if hasattr(inv.status, "value") else str(inv.status)
        response.append(
            FamilyInvitationResponse(
                id=inv.id,
                email=inv.email,
                status=status_value,
                created_at=inv.created_at,
                expires_at=inv.expires_at,
            )
        )

    return response


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_family_invitation(
    invitation_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cancela convite pendente (apenas owner/admin da familia)"""
    require_license(current_user)
    require_can_invite(current_user)

    invitation_result = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    invitation = invitation_result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    # Verificar se o convite eh da mesma licenca
    if invitation.license_id != current_user.license_id:
        raise HTTPException(status_code=403, detail="Convite nao pertence a sua familia")

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail="Convite ja foi aceito ou cancelado")

    invitation.status = InvitationStatus.CANCELLED
    await db.commit()


@router.post("/invitations/{invitation_id}/resend", status_code=status.HTTP_200_OK)
async def resend_family_invitation(
    invitation_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Reenvia email de convite"""
    require_license(current_user)
    require_can_invite(current_user)

    invitation_result = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
    invitation = invitation_result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    if invitation.license_id != current_user.license_id:
        raise HTTPException(status_code=403, detail="Convite nao pertence a sua familia")

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail="Convite nao esta pendente")

    # Enviar email novamente
    invite_url = f"{settings.frontend_url}/invite/{invitation.token}"
    email_sent = email_service.send_invitation(
        to_email=invitation.email,
        invite_url=invite_url,
        inviter_name=current_user.name,
    )

    if not email_sent:
        raise HTTPException(status_code=500, detail="Falha ao enviar email")

    return {"message": "Email reenviado com sucesso"}


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_family_member(
    member_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove membro da familia (apenas owner pode remover)"""
    require_license(current_user)

    # Verificar se o usuario eh owner da familia
    if not current_user.household_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuario nao pertence a nenhuma familia"
        )

    if current_user.household_membership.role != HouseholdRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o proprietario pode remover membros",
        )

    # Buscar membro a ser removido
    member_result = await db.execute(select(HouseholdMember).where(HouseholdMember.id == member_id))
    member = member_result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Membro nao encontrado")

    # Verificar se pertence a mesma licenca
    if member.license_id != current_user.license_id:
        raise HTTPException(status_code=403, detail="Membro nao pertence a sua familia")

    # Nao pode remover a si mesmo
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Voce nao pode remover a si mesmo")

    # Nao pode remover outro owner
    if member.role == HouseholdRole.OWNER.value:
        raise HTTPException(status_code=400, detail="Nao e possivel remover o proprietario")

    # Buscar usuario para limpar a licenca dele
    user_result = await db.execute(select(User).where(User.id == member.user_id))
    user = user_result.scalar_one_or_none()

    if user:
        user.license_id = None

    # Remover membership
    await db.delete(member)
    await db.commit()
