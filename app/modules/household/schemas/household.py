"""
Schemas de household: membros da familia, contexto e convites.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.email_address import NormalizedEmail
from app.models.household import HouseholdRole, OwnershipType

# ========== Household Member Schemas ==========


class HouseholdMemberBase(BaseModel):
    nickname: str | None = None
    can_create_transactions: bool = True
    can_edit_shared: bool = True
    can_invite_members: bool = False
    can_see_all: bool = False


class HouseholdMemberCreate(HouseholdMemberBase):
    user_id: int
    role: str = HouseholdRole.MEMBER.value


class HouseholdMemberResponse(HouseholdMemberBase):
    id: int
    license_id: int
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    role: str
    joined_at: datetime
    invited_by_id: int | None = None
    # parte nas despesas da casa (%); nulo = divisão igual
    share_percent: float | None = None

    class Config:
        from_attributes = True


class HouseholdMemberUpdate(BaseModel):
    nickname: str | None = None
    role: str | None = None
    can_create_transactions: bool | None = None
    can_edit_shared: bool | None = None
    can_invite_members: bool | None = None
    can_see_all: bool | None = None


# ========== Family Context Schemas ==========


class FamilyContext(BaseModel):
    """Contexto da familia do usuario logado"""

    license_id: int
    license_type: str
    is_owner: bool
    can_invite: bool
    member_count: int
    max_members: int
    members: list[HouseholdMemberResponse]


# ========== Family Invite Schemas ==========


class FamilyCreateRequest(BaseModel):
    """Request opcional para iniciar um grupo familiar"""

    nickname: str | None = None


class FamilyInviteRequest(BaseModel):
    """Request para convidar membro da familia"""

    email: NormalizedEmail
    nickname: str | None = None


class FamilyInviteResponse(BaseModel):
    """Response do convite da familia"""

    invitation_id: int
    email: str
    status: str
    expires_at: datetime
    code: str | None = None
    token: str | None = None
    invite_url: str | None = None


# ========== Pending Invitations ==========


class FamilyInvitationResponse(BaseModel):
    """Convite pendente da familia"""

    id: int
    email: str
    status: str
    created_at: datetime
    expires_at: datetime


# ========== Ownership Type ==========


class OwnershipUpdate(BaseModel):
    """Update para ownership_type de um recurso"""

    ownership_type: OwnershipType = OwnershipType.PERSONAL


# ========== Divisão das despesas da casa ==========


class FamilySplitMember(BaseModel):
    member_id: int
    user_id: int
    name: str
    is_me: bool
    share_percent: float  # parte usada no cálculo (igual ou definida)
    paid: float  # despesas da casa que este membro pagou no mês
    expenses_count: int
    fair_share: float  # quanto caberia a ele pela parte
    settled_out: float  # acertos que ele já pagou
    settled_in: float  # acertos que ele já recebeu
    balance: float  # > 0 tem a receber; < 0 tem a pagar


class FamilyTransfer(BaseModel):
    """Transferência sugerida para zerar os saldos"""

    from_user_id: int
    from_name: str
    to_user_id: int
    to_name: str
    amount: float


class FamilyCategoryTotal(BaseModel):
    name: str
    amount: float


class FamilySettlementResponse(BaseModel):
    id: int
    from_user_id: int
    to_user_id: int
    amount: float
    note: str | None = None
    created_at: datetime


class FamilySplitResponse(BaseModel):
    """
    Quem pagou o quê nas despesas da casa no mês e quem deve a quem.

    split_mode: equal (partes iguais) ou custom (porcentagens definidas pelo dono,
    por exemplo proporcionais à renda). transfers vazio = mês acertado.
    """

    year: int
    month: int
    total: float
    split_mode: str
    is_settled: bool
    members: list[FamilySplitMember]
    transfers: list[FamilyTransfer]
    categories: list[FamilyCategoryTotal]
    settlements: list[FamilySettlementResponse]


class FamilySettlementCreate(BaseModel):
    """Registra um acerto ("Acertar"): from_user pagou to_user por fora (Pix, dinheiro)"""

    to_user_id: int
    amount: float = Field(gt=0, le=1_000_000)
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    # quem pagou; padrão = quem registra
    from_user_id: int | None = None
    note: str | None = Field(default=None, max_length=200)


class FamilyShare(BaseModel):
    member_id: int
    share_percent: float = Field(ge=0, le=100)


class FamilySharesUpdate(BaseModel):
    """Partes de cada membro (somam 100). Lista vazia volta para a divisão igual"""

    shares: list[FamilyShare]


class FamilyJoinRequest(BaseModel):
    """Entrar numa família com o código do convite, já tendo conta no Koin"""

    code: str = Field(min_length=6, max_length=64)
