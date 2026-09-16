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

from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.security import get_password_hash
from app.models.user import User
from app.modules.auth.services.user_setup import setup_new_user


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
        print("Exemplo: python scripts/create_admin.py admin@exemplo.com senha123 'Administrador'")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    name = sys.argv[3]

    asyncio.run(create_admin(email, password, name))
