from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.category import Category
from app.modules.categories.schemas.category import CategoryCreate, CategoryResponse

router = APIRouter()


@router.get("", response_model=list[CategoryResponse])
async def list_categories(current_user: CurrentUser, db: DbSession):
    """Lista todas as categorias do usuario (padrao + personalizadas)"""
    # Retorna apenas categorias do usuario (tanto is_system=True quanto False)
    # Cada usuario tem suas proprias categorias criadas no setup inicial
    result = await db.execute(select(Category).where(Category.user_id == current_user.id))
    return result.scalars().all()


@router.post("", response_model=CategoryResponse, status_code=201)
async def create_category(
    data: CategoryCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria uma categoria personalizada"""
    category = Category(
        user_id=current_user.id,
        name=data.name,
        type=data.type,
        icon=data.icon,
        color=data.color,
        parent_id=data.parent_id,
        is_system=False,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove uma categoria personalizada (nao pode remover categorias do sistema)"""
    result = await db.execute(
        select(Category).where(
            Category.id == category_id,
            Category.user_id == current_user.id,
            Category.is_system == False,
        )
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=404,
            detail="Categoria nao encontrada ou e uma categoria do sistema",
        )

    await db.delete(category)
    await db.commit()
