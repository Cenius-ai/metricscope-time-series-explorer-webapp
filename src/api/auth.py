"""Auth API: login, session lookup, logout."""

from __future__ import annotations

from typing import Any

from .. import db
from .. import auth as credentials

INVALID_CREDENTIALS = "Invalid username or password."


class Unauthorized(Exception):
    """Raised when a token is missing, unknown or expired."""


def login(identifier: str, password: str, db_path=None) -> dict[str, Any]:
    """Validate credentials and create a session. Raises ValueError on bad input."""
    with db.get_conn(db_path) as conn:
        user = credentials.authenticate(conn, identifier, password)
        if user is None:
            raise ValueError(INVALID_CREDENTIALS)
        token = credentials.create_session(conn, int(user["id"]))
        return {
            "token": token,
            "user": {
                "id": int(user["id"]),
                "username": user["username"],
                "email": user["email"],
            },
        }


def session(token: str | None, db_path=None) -> dict[str, Any]:
    """Return the signed-in user for a token, or raise Unauthorized."""
    with db.get_conn(db_path) as conn:
        user = credentials.session_user(conn, token)
    if user is None:
        raise Unauthorized("Session expired or unknown.")
    return user


def logout(token: str | None, db_path=None) -> dict[str, bool]:
    """Delete the session row; the token can never be used again."""
    with db.get_conn(db_path) as conn:
        credentials.revoke_session(conn, token)
    return {"ok": True}
