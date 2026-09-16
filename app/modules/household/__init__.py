"""
Modulo Household - Gerenciamento de Familia/Household

Este modulo e responsavel por:
- Gerenciamento de membros da familia (household)
- Contexto da familia do usuario logado
- Convites para novos membros da familia
- Permissoes e roles dentro da familia (owner, member)
- Controle de acesso a recursos compartilhados

Estrutura:
- schemas/: Definicoes de schemas Pydantic para validacao de dados
  - household.py: HouseholdMemberResponse, FamilyContext, FamilyInviteRequest, etc.

- routers/: Endpoints da API
  - family.py: /context, /members, /invite, /invitations

Uso:
    from app.modules.household.schemas import FamilyContext, HouseholdMemberResponse
    from app.modules.household.routers import family_router

Dependencias:
- app.models.household: HouseholdMember, HouseholdRole, OwnershipType
- app.models: User, License, Invitation, InvitationStatus
- app.services.email_service: Para envio de convites por email
"""

from app.modules.household.routers import family_router
from app.modules.household.schemas import (
    FamilyContext,
    FamilyInvitationResponse,
    FamilyInviteRequest,
    FamilyInviteResponse,
    HouseholdMemberBase,
    HouseholdMemberCreate,
    HouseholdMemberResponse,
    HouseholdMemberUpdate,
    OwnershipUpdate,
)

__all__ = [
    # Schemas
    "HouseholdMemberBase",
    "HouseholdMemberCreate",
    "HouseholdMemberResponse",
    "HouseholdMemberUpdate",
    "FamilyContext",
    "FamilyInviteRequest",
    "FamilyInviteResponse",
    "FamilyInvitationResponse",
    "OwnershipUpdate",
    # Routers
    "family_router",
]
