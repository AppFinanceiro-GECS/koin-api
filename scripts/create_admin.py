#!/usr/bin/env python3
"""
Script para criar o primeiro usuário admin.
Execute com: python scripts/create_admin.py
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.email_address import NormalizedEmail
from app.core.security import get_password_hash, validate_password_or_raise
from app.models.user import User
from app.modules.auth.services.user_setup import setup_new_user


class AdminInputError(Exception):
    """E-mail ou senha recusados pela mesma regra da API."""


def validated_admin_credentials(email: str, password: str) -> str:
    try:
        normalized = TypeAdapter(NormalizedEmail).validate_python(email)
    except ValidationError as exc:
        raise AdminInputError(f"E-mail inválido: {email}") from exc

    try:
        validate_password_or_raise(password)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            listed = "; ".join(detail.get("errors", [])) or detail.get("message", "Senha inválida")
            raise AdminInputError(listed) from exc
        raise AdminInputError(str(detail)) from exc

    return normalized


async def create_admin(email: str, password: str, name: str):
    async with async_session_maker() as db:
        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Usuário {email} já existe!")
            if not existing.is_admin:
                existing.is_admin = True
                await db.commit()
                print("Usuário promovido a admin!")
            return

        # Create admin user
        user = User(
            email=email,
            name=name,
            hashed_password=get_password_hash(password),
            is_admin=True,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

        # Setup initial data (accounts, categories)
        await setup_new_user(db, user.id)

        await db.commit()
        print("Admin criado com sucesso!")
        print(f"  Email: {email}")
        print(f"  Nome: {name}")
        print(f"  ID: {user.id}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python scripts/create_admin.py <email> <senha> <nome>")
        print(
            "Exemplo: python scripts/create_admin.py admin@exemplo.com "
            "'frase-longa-do-admin' 'Administrador'"
        )
        sys.exit(1)

    try:
        email = validated_admin_credentials(sys.argv[1], sys.argv[2])
    except AdminInputError as exc:
        print(exc)
        sys.exit(1)

    password = sys.argv[2]
    name = sys.argv[3]

    asyncio.run(create_admin(email, password, name))
