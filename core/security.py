"""Verificación del Bearer token (comparación de tiempo constante)."""
from __future__ import annotations

import hmac

from core.errors import AuthError


def verify_token(authorization: str | None, expected_token: str) -> None:
    """Valida el header `Authorization: Bearer <token>`.

    Usa `hmac.compare_digest` para evitar ataques de timing. Lanza `AuthError`
    (401) si el header falta o el token no coincide.
    """
    if not authorization:
        raise AuthError("Falta el header Authorization")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Formato de Authorization inválido; se espera 'Bearer <token>'")

    if not hmac.compare_digest(token, expected_token):
        raise AuthError("Token inválido")
