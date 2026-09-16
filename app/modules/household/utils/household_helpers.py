"""
Helpers para lógica de household reutilizáveis em todos os módulos
"""

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.household import HouseholdMember
from app.models.user import User


async def get_household_user_ids(db: AsyncSession, user: User) -> list[int]:
    """
    Retorna lista de user_ids de todos os membros da mesma household.
    Se usuário não tem license_id, retorna lista vazia.

    Args:
        db: Sessão do banco de dados
        user: Usuário atual

    Returns:
        Lista de IDs dos usuários da household, ou lista vazia se não houver household
    """
    if not user.license_id:
        return []

    result = await db.execute(
        select(HouseholdMember.user_id).where(HouseholdMember.license_id == user.license_id)
    )
    return list(result.scalars().all())


async def get_household_member(db: AsyncSession, user: User) -> HouseholdMember | None:
    """
    Retorna o HouseholdMember do usuário atual.

    Args:
        db: Sessão do banco de dados
        user: Usuário atual

    Returns:
        HouseholdMember ou None se usuário não está em household
    """
    if not user.license_id:
        return None

    result = await db.execute(
        select(HouseholdMember).where(
            HouseholdMember.user_id == user.id, HouseholdMember.license_id == user.license_id
        )
    )
    return result.scalar_one_or_none()


def build_ownership_filter(
    model,
    user_id_field,
    ownership_field,
    current_user_id: int,
    household_user_ids: list[int],
    member: HouseholdMember | None = None,
):
    """
    Constrói filtro SQLAlchemy padrão para ownership.

    Args:
        model: Classe do modelo SQLAlchemy
        user_id_field: Campo user_id do modelo (ex: Transaction.user_id)
        ownership_field: Campo ownership_type do modelo (ex: Transaction.ownership_type)
        current_user_id: ID do usuário atual
        household_user_ids: Lista de IDs da household
        member: HouseholdMember opcional para verificar can_see_all

    Returns:
        Expressão SQLAlchemy para usar em .where()

    Examples:
        >>> from app.models.transaction import Transaction
        >>> filter_expr = build_ownership_filter(
        ...     Transaction,
        ...     Transaction.user_id,
        ...     Transaction.ownership_type,
        ...     current_user_id=1,
        ...     household_user_ids=[1, 2, 3]
        ... )
        >>> query = select(Transaction).where(filter_expr)
    """
    # Se member tem can_see_all, vê TODOS os recursos de TODOS os membros
    if member and member.can_see_all:
        return user_id_field.in_(household_user_ids)

    # Lógica padrão
    if household_user_ids:
        return or_(
            # Recursos PERSONAL do usuário atual
            and_(user_id_field == current_user_id, ownership_field == "personal"),
            # Recursos HOUSEHOLD de qualquer membro
            and_(user_id_field.in_(household_user_ids), ownership_field == "household"),
        )
    else:
        # Sem household, apenas recursos do próprio usuário
        return user_id_field == current_user_id


async def validate_create_permission(db: AsyncSession, user: User, ownership_type: str) -> None:
    """
    Valida se usuário tem permissão para criar recurso com ownership_type especificado.
    Levanta HTTPException 403 se não tiver permissão.

    Args:
        db: Sessão do banco de dados
        user: Usuário atual
        ownership_type: Tipo de propriedade ("personal" ou "household")

    Raises:
        HTTPException: 403 se não tiver permissão

    Examples:
        >>> await validate_create_permission(db, user, "household")
        # Sucesso: sem exceção
        >>> await validate_create_permission(db, member_sem_permissao, "household")
        # Levanta: HTTPException 403
    """
    if ownership_type == "personal":
        return  # Sempre permitido

    # household - verificar permissões
    member = await get_household_member(db, user)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não está em uma família para criar recursos compartilhados",
        )

    if not member.can_create_transactions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para criar recursos compartilhados",
        )


async def validate_edit_permission(
    db: AsyncSession, user: User, resource_user_id: int, resource_ownership: str
) -> None:
    """
    Valida se usuário tem permissão para editar recurso.
    Levanta HTTPException 403 se não tiver permissão.

    Args:
        db: Sessão do banco de dados
        user: Usuário atual
        resource_user_id: ID do criador do recurso
        resource_ownership: Tipo de propriedade do recurso

    Raises:
        HTTPException: 403 se não tiver permissão

    Examples:
        >>> # Criador sempre pode editar
        >>> await validate_edit_permission(db, user, user.id, "household")
        # Sucesso
        >>> # Outro usuário tentando editar personal
        >>> await validate_edit_permission(db, user1, user2.id, "personal")
        # Levanta: HTTPException 403
    """
    # Criador sempre pode editar
    if resource_user_id == user.id:
        return

    # Recurso de outro usuário
    if resource_ownership == "personal":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não pode editar recursos pessoais de outros membros",
        )

    # household - verificar permissão
    member = await get_household_member(db, user)
    if not member or not member.can_edit_shared:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para editar recursos compartilhados",
        )


async def validate_delete_permission(
    db: AsyncSession, user: User, resource_user_id: int, resource_ownership: str
) -> None:
    """
    Valida se usuário tem permissão para excluir recurso.
    Levanta HTTPException 403 se não tiver permissão.

    Args:
        db: Sessão do banco de dados
        user: Usuário atual
        resource_user_id: ID do criador do recurso
        resource_ownership: Tipo de propriedade do recurso

    Raises:
        HTTPException: 403 se não tiver permissão

    Examples:
        >>> # Criador sempre pode excluir
        >>> await validate_delete_permission(db, user, user.id, "household")
        # Sucesso
        >>> # Owner pode excluir household de outros
        >>> await validate_delete_permission(db, owner, other_user.id, "household")
        # Sucesso se owner.role == "owner"
    """
    # Criador sempre pode excluir
    if resource_user_id == user.id:
        return

    # Verificar se é owner da license
    member = await get_household_member(db, user)
    if member and member.role == "owner":
        # Owner pode excluir recursos household de qualquer membro
        if resource_ownership == "household":
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Apenas o criador ou dono da família pode excluir este recurso",
    )
