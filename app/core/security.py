import hashlib
import re
import secrets
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from jose import jwt
from passlib.context import CryptContext

from app.core.utils import utc_now

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Common passwords list (basic list - can be expanded)
COMMON_PASSWORDS = {
    "password",
    "123456",
    "12345678",
    "qwerty",
    "abc123",
    "monkey",
    "1234567",
    "letmein",
    "trustno1",
    "dragon",
    "baseball",
    "iloveyou",
    "master",
    "sunshine",
    "ashley",
    "bailey",
    "shadow",
    "123123",
    "654321",
    "superman",
    "qazwsx",
    "michael",
    "football",
    "password1",
    "password123",
    "welcome",
    "jesus",
    "ninja",
    "mustang",
    "password2",
    "admin",
    "login",
    "passw0rd",
    "hello",
    "charlie",
    "donald",
    "password1234",
    "qwerty123",
    "senha",
    "senha123",
}


def validate_password_strength(password: str) -> dict:
    """
    Validates password strength and returns validation result.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    - Not a common password
    """
    errors = []

    if len(password) < 8:
        errors.append("Senha deve ter no mínimo 8 caracteres")

    if len(password) > 128:
        errors.append("Senha deve ter no máximo 128 caracteres")

    if not re.search(r"[A-Z]", password):
        errors.append("Senha deve conter pelo menos uma letra maiúscula")

    if not re.search(r"[a-z]", password):
        errors.append("Senha deve conter pelo menos uma letra minúscula")

    if not re.search(r"\d", password):
        errors.append("Senha deve conter pelo menos um número")

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", password):
        errors.append("Senha deve conter pelo menos um caractere especial (!@#$%^&*)")

    if password.lower() in COMMON_PASSWORDS:
        errors.append("Senha muito comum. Escolha uma senha mais segura")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "strength": _calculate_password_strength(password, errors),
    }


def _calculate_password_strength(password: str, errors: list) -> str:
    """Calculate password strength score"""
    if errors:
        return "fraca"

    score = 0

    # Length bonus
    if len(password) >= 12:
        score += 2
    elif len(password) >= 10:
        score += 1

    # Variety bonus
    if re.search(r"[A-Z].*[A-Z]", password):  # Multiple uppercase
        score += 1
    if re.search(r"\d.*\d", password):  # Multiple numbers
        score += 1
    if re.search(r"[!@#$%^&*(),.?\":{}|<>].*[!@#$%^&*(),.?\":{}|<>]", password):  # Multiple special
        score += 1

    if score >= 4:
        return "muito forte"
    elif score >= 2:
        return "forte"
    else:
        return "média"


def validate_password_or_raise(password: str) -> None:
    """Validate password and raise HTTPException if invalid"""
    result = validate_password_strength(password)
    if not result["is_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Senha não atende aos requisitos de segurança",
                "errors": result["errors"],
            },
        )


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    if expires_delta:
        expire = utc_now() + expires_delta
    else:
        expire = utc_now() + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str | Any) -> str:
    expire = utc_now() + timedelta(days=settings.refresh_token_expire_days)
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except jwt.JWTError:
        return None


# ============== API Key Functions ==============


def generate_api_key() -> tuple[str, str, str]:
    """
    Gera uma nova API Key.
    Retorna: (key_completa, key_prefix, key_hash)

    Formato: biv_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (36 chars total)
    - Prefixo: biv_ (4 chars)
    - Random: 32 chars hex

    A chave completa só é mostrada uma vez ao usuário.
    Armazenamos apenas o hash e o prefixo.
    """
    random_part = secrets.token_hex(16)  # 32 chars hex
    full_key = f"biv_{random_part}"
    key_prefix = full_key[:12]  # biv_xxxxxxxx
    key_hash = hash_api_key(full_key)

    return full_key, key_prefix, key_hash


def hash_api_key(api_key: str) -> str:
    """
    Cria hash SHA-256 da API key para armazenamento seguro.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key_format(api_key: str) -> bool:
    """
    Verifica se a API key está no formato correto.
    Formato esperado: biv_[32 chars hex]
    """
    if not api_key.startswith("biv_"):
        return False
    if len(api_key) != 36:
        return False
    # Verifica se a parte após biv_ é hexadecimal
    hex_part = api_key[4:]
    try:
        int(hex_part, 16)
        return True
    except ValueError:
        return False
