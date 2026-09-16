"""
Cryptography utilities for encrypting/decrypting sensitive data.

Uses Fernet symmetric encryption with a key derived from the application's secret_key.
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from .config import settings


def _get_encryption_key() -> bytes:
    """
    Derive encryption key from secret_key.

    Uses SHA-256 to create a consistent 32-byte key from the secret_key,
    then encodes it in the format required by Fernet.

    Returns:
        bytes: Base64-encoded encryption key
    """
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key)


def encrypt_password(password: str) -> str:
    """
    Encrypt password using Fernet symmetric encryption.

    Args:
        password: Plain text password to encrypt

    Returns:
        str: Encrypted password as base64 string

    Example:
        >>> encrypted = encrypt_password("mypassword123")
        >>> encrypted.startswith("gAAAAA")
        True
    """
    f = Fernet(_get_encryption_key())
    return f.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """
    Decrypt password previously encrypted with encrypt_password().

    Args:
        encrypted: Base64-encoded encrypted password

    Returns:
        str: Decrypted plain text password

    Raises:
        cryptography.fernet.InvalidToken: If encryption key changed or data is corrupted

    Example:
        >>> encrypted = encrypt_password("mypassword123")
        >>> decrypt_password(encrypted)
        'mypassword123'
    """
    f = Fernet(_get_encryption_key())
    return f.decrypt(encrypted.encode()).decode()
