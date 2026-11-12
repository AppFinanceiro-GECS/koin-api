"""
Rotas para gerenciamento de familia/household.
Permite ao owner convidar membros e gerenciar a familia.
"""

import asyncio
import logging
import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.email_address import normalize_email
from app.core.services.email_service import email_service
from app.core.utils import today_br, utc_now
from app.models import Invitation, InvitationStatus, License, User
from app.models.household import HouseholdMember, HouseholdRole, HouseholdSettlement
from app.models.license import LicenseStatus, LicenseType
from app.modules.household.schemas.household import (
    FamilyCategoryTotal,
    FamilyContext,
    FamilyCreateRequest,
    FamilyInvitationResponse,
    FamilyInviteRequest,
    FamilyInviteResponse,
    FamilyJoinRequest,
    FamilySettlementCreate,
    FamilySettlementResponse,
    FamilySharesUpdate,
    FamilySplitMember,
    FamilySplitResponse,
    FamilyTransfer,
    HouseholdMemberResponse,
)
from app.modules.household.services.family_split import build_family_split

logger = logging.getLogger(__name__)


router = APIRouter()


def require_license(user: User):
    """Verifica se o usuario tem licenca"""
    if not user.license_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuário não possui licença"
        )


async def count_members(db, license_id: int) -> int:
    return (
        await db.scalar(
            select(func.count(HouseholdMember.id)).where(HouseholdMember.license_id == license_id)
        )
    ) or 0


def require_can_invite(user: User):
    """Verifica se o usuario pode convidar membros"""
    if not user.household_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuário não pertence a nenhuma família"
        )
    if not user.household_membership.can_invite_members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para convidar membros"
        )


@router.post("", response_model=FamilyContext, status_code=status.HTTP_201_CREATED)
async def create_family(
    current_user: CurrentUser,
    db: DbSession,
    data: FamilyCreateRequest | None = None,
):
    """Inicializa um grupo familiar para o usuário atual, provisionando a licença e tornando-o owner."""
    if current_user.household_membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já pertence a uma família",
        )

    license = None
    if current_user.license_id:
        license_result = await db.execute(
            select(License).where(License.id == current_user.license_id)
        )
        license = license_result.scalar_one_or_none()

    if not license:
        key = secrets.token_urlsafe(32)
        license = License(
            key=key,
            type=LicenseType.PREMIUM,
            status=LicenseStatus.ACTIVE,
            max_users=5,
            has_ai_assistant=True,
            has_insights=True,
            has_debt_strategies=True,
            has_goals=True,
            has_budget=True,
            owner_user_id=current_user.id,
            owner_email=current_user.email,
        )
        db.add(license)
        await db.flush()
        current_user.license_id = license.id
    else:
        if license.max_users < 5:
            license.max_users = 5
        if not license.owner_user_id:
            license.owner_user_id = current_user.id
            license.owner_email = current_user.email

    member = HouseholdMember(
        license_id=license.id,
        user_id=current_user.id,
        role=HouseholdRole.OWNER.value,
        nickname=data.nickname if data and data.nickname else None,
        can_create_transactions=True,
        can_edit_shared=True,
        can_invite_members=True,
        can_see_all=True,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    await db.refresh(license)
    await db.refresh(current_user)

    return await get_family_context(current_user, db)


@router.get("/context", response_model=FamilyContext)
async def get_family_context(current_user: CurrentUser, db: DbSession):
    """Retorna contexto da familia do usuario logado"""
    require_license(current_user)
    if not current_user.household_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuário não pertence a nenhuma família"
        )

    # Buscar licenca
    license_result = await db.execute(select(License).where(License.id == current_user.license_id))
    license = license_result.scalar_one_or_none()

    if not license:
        raise HTTPException(status_code=404, detail="Licença não encontrada")

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
                share_percent=float(m.share_percent) if m.share_percent is not None else None,
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
                share_percent=float(m.share_percent) if m.share_percent is not None else None,
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
        raise HTTPException(status_code=404, detail="Licença não encontrada")

    # Verificar limite de usuarios (members é noload: conta no banco)
    if await count_members(db, license.id) >= license.max_users:
        raise HTTPException(
            status_code=400, detail=f"Limite de {license.max_users} membros atingido"
        )

    # Quem já tem conta no Koin também pode ser convidado: entra com o código
    # (POST /family/join) em vez de criar outra conta
    existing_user = await db.scalar(select(User).where(User.email == data.email))
    if existing_user:
        existing_member = await db.scalar(
            select(HouseholdMember).where(
                HouseholdMember.license_id == license.id,
                HouseholdMember.user_id == existing_user.id,
            )
        )
        if existing_member:
            raise HTTPException(status_code=400, detail="Usuário já é membro desta família")

    # Verificar se ja existe convite pendente
    existing_invite = await db.scalar(
        select(Invitation).where(
            Invitation.email == data.email, Invitation.status == InvitationStatus.PENDING
        )
    )
    if existing_invite:
        raise HTTPException(status_code=400, detail="Já existe um convite pendente para este email")

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
    email_sent = await asyncio.to_thread(
        email_service.send_invitation,
        to_email=data.email,
        invite_url=invite_url,
        inviter_name=current_user.name,
        invite_code=invitation.token,
    )

    if not email_sent:
        logger.warning("email_delivery_failed")

    # Status pode ser Enum ou string dependendo de como foi carregado
    status_value = (
        invitation.status.value if hasattr(invitation.status, "value") else str(invitation.status)
    )

    return FamilyInviteResponse(
        invitation_id=invitation.id,
        email=invitation.email,
        status=status_value,
        expires_at=invitation.expires_at,
        code=invitation.token,
        token=invitation.token,
        invite_url=invite_url,
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
        raise HTTPException(status_code=404, detail="Convite não encontrado")

    # Verificar se o convite eh da mesma licenca
    if invitation.license_id != current_user.license_id:
        raise HTTPException(status_code=403, detail="Convite não pertence à sua família")

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail="Convite já foi aceito ou cancelado")

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
        raise HTTPException(status_code=404, detail="Convite não encontrado")

    if invitation.license_id != current_user.license_id:
        raise HTTPException(status_code=403, detail="Convite não pertence à sua família")

    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail="Convite não está pendente")

    # Enviar email novamente
    invite_url = f"{settings.frontend_url}/invite/{invitation.token}"
    email_sent = await asyncio.to_thread(
        email_service.send_invitation,
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuário não pertence a nenhuma família"
        )

    if current_user.household_membership.role != HouseholdRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o proprietário pode remover membros",
        )

    # Buscar membro a ser removido
    member_result = await db.execute(select(HouseholdMember).where(HouseholdMember.id == member_id))
    member = member_result.scalar_one_or_none()

    if not member:
        raise HTTPException(status_code=404, detail="Membro não encontrado")

    # Verificar se pertence a mesma licenca
    if member.license_id != current_user.license_id:
        raise HTTPException(status_code=403, detail="Membro não pertence à sua família")

    # Nao pode remover a si mesmo
    if member.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo")

    # Nao pode remover outro owner
    if member.role == HouseholdRole.OWNER.value:
        raise HTTPException(status_code=400, detail="Não é possível remover o proprietário")

    # Buscar usuario para limpar a licenca dele
    user_result = await db.execute(select(User).where(User.id == member.user_id))
    user = user_result.scalar_one_or_none()

    if user:
        user.license_id = None

    # Remover membership
    await db.delete(member)
    await db.commit()


# ========== Divisão das despesas da casa ==========


def require_family(user: User) -> HouseholdMember:
    require_license(user)
    if not user.household_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Usuário não pertence a nenhuma família"
        )
    return user.household_membership


def _split_response(split, current_user_id: int) -> FamilySplitResponse:
    return FamilySplitResponse(
        year=split.year,
        month=split.month,
        total=float(split.total),
        split_mode=split.split_mode,
        is_settled=split.is_settled,
        members=[
            FamilySplitMember(
                member_id=m.member_id,
                user_id=m.user_id,
                name=m.name,
                is_me=m.user_id == current_user_id,
                share_percent=float(m.share_percent),
                paid=float(m.paid),
                expenses_count=m.expenses_count,
                fair_share=float(m.fair_share),
                settled_out=float(m.settled_out),
                settled_in=float(m.settled_in),
                balance=float(m.balance),
            )
            for m in split.members
        ],
        transfers=[
            FamilyTransfer(
                from_user_id=t.from_user_id,
                from_name=t.from_name,
                to_user_id=t.to_user_id,
                to_name=t.to_name,
                amount=float(t.amount),
            )
            for t in split.transfers
        ],
        categories=[
            FamilyCategoryTotal(name=c.name, amount=float(c.amount)) for c in split.categories
        ],
        settlements=[
            FamilySettlementResponse(
                id=s.id,
                from_user_id=s.from_user_id,
                to_user_id=s.to_user_id,
                amount=float(s.amount),
                note=s.note,
                created_at=s.created_at,
            )
            for s in split.settlements
        ],
    )


@router.get("/split", response_model=FamilySplitResponse)
async def family_split(
    current_user: CurrentUser,
    db: DbSession,
    year: int | None = None,
    month: int | None = None,
):
    """
    Divisão das despesas da casa no mês: quanto cada membro pagou do que foi marcado como
    da família, a parte de cada um e as transferências que zeram os saldos.
    """
    membership = require_family(current_user)
    today = today_br()
    year = year or today.year
    month = month or today.month
    if not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="Mês inválido")
    split = await build_family_split(db, membership.license_id, year, month)
    return _split_response(split, current_user.id)


@router.post(
    "/settlements", response_model=FamilySplitResponse, status_code=status.HTTP_201_CREATED
)
async def create_settlement(data: FamilySettlementCreate, current_user: CurrentUser, db: DbSession):
    """
    Registra um acerto entre membros (o dinheiro passa por fora, por Pix ou dinheiro).
    Devolve a divisão do mês já com o acerto.
    """
    membership = require_family(current_user)
    from_user_id = data.from_user_id or current_user.id
    if from_user_id == data.to_user_id:
        raise HTTPException(
            status_code=422, detail="Quem paga e quem recebe precisam ser diferentes"
        )
    # só quem pagou ou recebeu, ou o dono da família, registra o acerto
    if current_user.id not in (from_user_id, data.to_user_id) and not membership.is_admin:
        raise HTTPException(status_code=403, detail="Sem permissão para registrar este acerto")
    member_ids = set(
        (
            await db.execute(
                select(HouseholdMember.user_id).where(
                    HouseholdMember.license_id == membership.license_id
                )
            )
        )
        .scalars()
        .all()
    )
    if {from_user_id, data.to_user_id} - member_ids:
        raise HTTPException(status_code=422, detail="Os dois precisam ser membros da família")

    db.add(
        HouseholdSettlement(
            license_id=membership.license_id,
            from_user_id=from_user_id,
            to_user_id=data.to_user_id,
            amount=round(data.amount, 2),
            year=data.year,
            month=data.month,
            note=data.note,
            created_by_id=current_user.id,
        )
    )
    await db.commit()
    split = await build_family_split(db, membership.license_id, data.year, data.month)
    return _split_response(split, current_user.id)


@router.delete("/settlements/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_settlement(settlement_id: int, current_user: CurrentUser, db: DbSession):
    """Desfaz um acerto registrado por engano (quem registrou, quem participou ou o dono)"""
    membership = require_family(current_user)
    settlement = await db.scalar(
        select(HouseholdSettlement).where(
            HouseholdSettlement.id == settlement_id,
            HouseholdSettlement.license_id == membership.license_id,
        )
    )
    if not settlement:
        raise HTTPException(status_code=404, detail="Acerto não encontrado")
    involved = {settlement.from_user_id, settlement.to_user_id, settlement.created_by_id}
    if current_user.id not in involved and not membership.is_admin:
        raise HTTPException(status_code=403, detail="Sem permissão para desfazer este acerto")
    await db.delete(settlement)
    await db.commit()


@router.put("/shares", response_model=FamilyContext)
async def update_shares(data: FamilySharesUpdate, current_user: CurrentUser, db: DbSession):
    """
    Define a parte de cada membro nas despesas da casa (ex.: proporcional à renda).
    As partes precisam cobrir todos os membros e somar 100. Lista vazia = divisão igual.
    """
    membership = require_family(current_user)
    if not membership.is_admin:
        raise HTTPException(status_code=403, detail="Só o dono da família define a divisão")
    members = list(
        (
            await db.execute(
                select(HouseholdMember).where(HouseholdMember.license_id == membership.license_id)
            )
        )
        .scalars()
        .all()
    )
    if not data.shares:
        for m in members:
            m.share_percent = None
    else:
        by_id = {s.member_id: s.share_percent for s in data.shares}
        if set(by_id) != {m.id for m in members}:
            raise HTTPException(status_code=422, detail="Informe a parte de todos os membros")
        if abs(sum(by_id.values()) - 100) > 0.01:
            raise HTTPException(status_code=422, detail="As partes precisam somar 100%")
        for m in members:
            m.share_percent = round(by_id[m.id], 2)
    await db.commit()
    for m in members:
        await db.refresh(m)
    return await get_family_context(current_user, db)


# ========== Entrar com o código, já tendo conta ==========


@router.post("/join", response_model=FamilyContext)
async def join_family(data: FamilyJoinRequest, current_user: CurrentUser, db: DbSession):
    """
    Entra na família com o código do convite, para quem já tem conta no Koin.

    O convite precisa ter sido feito para o e-mail da conta. Quem está sozinho numa família
    própria sai dela ao entrar; quem divide família com outras pessoas precisa sair antes.
    Os lançamentos pessoais continuam pessoais: só o que for marcado como da família aparece
    para os outros membros.
    """
    invitation = await db.scalar(select(Invitation).where(Invitation.token == data.code.strip()))
    if not invitation or not invitation.license_id:
        raise HTTPException(status_code=404, detail="Convite não encontrado")
    if utc_now() > invitation.expires_at:
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.EXPIRED
            await db.commit()
        raise HTTPException(status_code=400, detail="Convite expirado. Peça um novo")
    if invitation.status != InvitationStatus.PENDING:
        raise HTTPException(status_code=400, detail="Este convite já foi usado ou cancelado")
    if normalize_email(invitation.email) != normalize_email(current_user.email):
        raise HTTPException(
            status_code=403,
            detail="Este convite foi enviado para outro e-mail. Peça um convite para o seu",
        )

    current = current_user.household_membership
    if current:
        if current.license_id == invitation.license_id:
            raise HTTPException(status_code=400, detail="Você já faz parte desta família")
        if await count_members(db, current.license_id) > 1:
            raise HTTPException(
                status_code=409,
                detail="Você já faz parte de outra família. Saia dela antes de entrar nesta",
            )
        # família só dele: sai dela para entrar na nova
        await db.delete(current)
        await db.flush()

    license = await db.scalar(select(License).where(License.id == invitation.license_id))
    if not license:
        raise HTTPException(status_code=404, detail="Família não encontrada")
    if await count_members(db, license.id) >= license.max_users:
        raise HTTPException(
            status_code=400, detail=f"A família já tem o limite de {license.max_users} membros"
        )

    db.add(
        HouseholdMember(
            license_id=license.id,
            user_id=current_user.id,
            role=HouseholdRole.MEMBER.value,
            invited_by_id=invitation.invited_by_id,
        )
    )
    current_user.license_id = license.id
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = utc_now()
    await db.commit()
    await db.refresh(current_user)
    return await get_family_context(current_user, db)
