"""Local credential handling: PBKDF2-HMAC-SHA256 hashes and session tokens."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import timedelta
from typing import Any

from . import config
from .db import iso, utcnow

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{3,64}$")
MIN_PASSWORD_LENGTH = 6


class AuthError(ValueError):
    """Raised for invalid credentials or unusable account input."""


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    """Return (password_hash, salt) as hex strings. Never persists plaintext."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, config.PBKDF2_ITERATIONS
    )
    return digest.hex(), salt.hex()


def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    if not password_hash or not salt_hex:
        return False
    candidate, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, password_hash)


def normalise_identifier(identifier: str) -> str:
    return (identifier or "").strip().lower()


def create_user(
    conn: sqlite3.Connection,
    username: str,
    email: str,
    password: str,
) -> int:
    username = (username or "").strip()
    email = normalise_identifier(email)
    if not USERNAME_RE.match(username):
        raise AuthError("Username must be 3-64 characters: letters, digits, . _ - @")
    if not USERNAME_RE.match(email):
        raise AuthError("Email is not a valid address")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    password_hash, salt = hash_password(password)
    cur = conn.execute(
        "INSERT INTO users (username, email, password_hash, salt, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (username, email, password_hash, salt, iso(utcnow())),
    )
    return int(cur.lastrowid)


def authenticate(conn: sqlite3.Connection, identifier: str, password: str) -> sqlite3.Row | None:
    """Return the user row for a valid username/email + password pair, else None."""
    ident = normalise_identifier(identifier)
    if not ident or not password:
        return None
    row = conn.execute(
        "SELECT * FROM users WHERE lower(username) = ? OR lower(email) = ?",
        (ident, ident),
    ).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"], row["salt"]):
        return None
    return row


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(days=config.SESSION_TTL_DAYS)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, iso(now), iso(expires)),
    )
    return token


def session_user(conn: sqlite3.Connection, token: str | None) -> dict[str, Any] | None:
    """Resolve a session token to a public user dict; expired/garbage tokens → None."""
    if not token:
        return None
    row = conn.execute(
        "SELECT s.token, s.expires_at, u.id, u.username, u.email, u.created_at"
        " FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    ).fetchone()
    if row is None:
        return None
    if row["expires_at"] <= iso(utcnow()):
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        return None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def revoke_session(conn: sqlite3.Connection, token: str | None) -> bool:
    if not token:
        return False
    cur = conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    return cur.rowcount > 0
