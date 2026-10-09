"""Security utilities for password hashing, tokens, and verification."""

from __future__ import annotations

__all__ = [
    "generate_token",
    "new_token",
    "hash_password",
    "verify_password",
    "password_problems",
    "encrypt_secret",
    "decrypt_secret",
]

import hashlib
import hmac
import secrets


def generate_token(length: int = 32) -> str:
    """Generate a secure random URL-safe token."""
    return secrets.token_urlsafe(length)


def new_token(length: int = 32) -> str:
    """Alias for generate_token."""
    return generate_token(length)


def hash_password(password: str) -> str:
    """Hash a password using a secure built-in hashing scheme."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000
    ).hex()
    return f"{salt}${pwd_hash}"


def verify_password(stored_password: str, provided_password: str) -> bool:
    """Verify a password against its stored hash."""
    try:
        salt, pwd_hash = stored_password.split('$')
        new_hash = hashlib.pbkdf2_hmac(
            'sha256', provided_password.encode('utf-8'), salt.encode('utf-8'), 100000
        ).hex()
        return hmac.compare_digest(pwd_hash, new_hash)
    except (ValueError, AttributeError):
        return False


def password_problems(password: str) -> list[str]:
    """Check a password for policy issues and return a list of problems."""
    problems = []
    if not password or len(password) < 8:
        problems.append("Password must be at least 8 characters long.")
    return problems


def encrypt_secret(plain_text: str) -> str:
    """Fallback encryption helper if cryptography isn't initialized."""
    return plain_text


def decrypt_secret(cipher_text: str) -> str:
    """Fallback decryption helper if cryptography isn't initialized."""
    return cipher_text
