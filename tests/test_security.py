"""Hashes do passlib e tokens do python-jose precisam continuar válidos."""

import app.core.security as security
from app.core.security import (
    create_access_token,
    decode_token,
    get_password_hash,
    verify_password,
)

# Gerado com passlib CryptContext(schemes=["bcrypt"]) para "TestPass123!".
PASSLIB_HASH = "$2b$12$/HTOc1sm9PmWv0/KYVBaCuImjZNO7t1/KfPj4LqFXV5iYNlthaqgO"

# Gerado com python-jose (HS256, sub=42, type=access, exp=2035-01-01 UTC).
JOSE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJleHAiOjIwNTEyMjI0MDAsInN1YiI6IjQyIiwidHlwZSI6ImFjY2VzcyJ9."
    "mJZ_x5ayhqipc0SXVBGojWOjl8Zr7wms-x5UZKeUxVo"
)
JOSE_SECRET = "test-secret-key"


def test_hash_do_passlib_continua_valido():
    assert verify_password("TestPass123!", PASSLIB_HASH)
    assert not verify_password("OutraSenha1!", PASSLIB_HASH)


def test_hash_novo_verifica_e_mantem_formato_bcrypt():
    hashed = get_password_hash("TestPass123!")
    assert hashed.startswith("$2b$")
    assert verify_password("TestPass123!", hashed)
    assert not verify_password("OutraSenha1!", hashed)


def test_senha_acima_de_72_bytes_usa_o_mesmo_corte_do_bcrypt():
    password = "a" * 80
    hashed = get_password_hash(password)
    assert verify_password(password, hashed)
    assert verify_password("a" * 72, hashed)
    assert not verify_password("a" * 71 + "b", hashed)


def test_token_do_python_jose_continua_valido(monkeypatch):
    monkeypatch.setattr(security.settings, "secret_key", JOSE_SECRET)
    monkeypatch.setattr(security.settings, "algorithm", "HS256")

    payload = decode_token(JOSE_TOKEN)

    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["type"] == "access"


def test_access_token_roundtrip():
    payload = decode_token(create_access_token(7))

    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["type"] == "access"


def test_token_invalido_retorna_none():
    assert decode_token("nao-e-um-jwt") is None
