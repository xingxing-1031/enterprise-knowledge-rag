"""Dependency-free demo authentication: pbkdf2 hashing + signed session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sys
import time
from collections.abc import Sequence

from fastapi import HTTPException, Request

from enterprise_knowledge_rag.config import Settings
from enterprise_knowledge_rag.models import UserContext, UserRole

_PBKDF2_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, _PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        _b64(salt),
        _b64(digest),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            _unb64(salt),
            int(iterations),
        )
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, TypeError):
        return False


def issue_session(
    *,
    user_id: str,
    role: UserRole,
    departments: Sequence[str],
    secret: str,
    ttl_seconds: int,
) -> str:
    payload = {
        "user_id": user_id,
        "role": role.value,
        "departments": ",".join(departments),
        "exp": int(time.time()) + ttl_seconds,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_signature(body, secret)}"


def read_session(token: str | None, secret: str) -> UserContext | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _signature(body, secret)):
        return None
    try:
        payload = json.loads(_unb64(body))
        if int(payload["exp"]) < int(time.time()):
            return None
        departments = {
            item for item in payload["departments"].split(",") if item
        }
        return UserContext(
            user_id=payload["user_id"],
            role=UserRole(payload["role"]),
            departments=departments,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


class AuthSessionResolver:
    """Resolve demo identity from a signed cookie; fail-fast when absent."""

    def __init__(self, settings: Settings) -> None:
        self._cookie_name = settings.auth_cookie_name
        self._secret = settings.auth_session_secret
        if not self._secret:
            raise ValueError("auth_session_secret must be configured")

    def resolve(self, request: Request) -> UserContext:
        context = read_session(
            request.cookies.get(self._cookie_name), self._secret
        )
        if context is None:
            raise HTTPException(status_code=401, detail="请先登录。")
        return context


def _signature(body: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def main() -> int:
    if len(sys.argv) > 1:
        for password in sys.argv[1:]:
            print(hash_password(password))
        return 0
    from getpass import getpass

    password = getpass("密码：")
    confirmation = getpass("再次输入：")
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致。")
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
