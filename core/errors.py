"""Jerarquía de errores del bridge + contrato de respuesta de error.

El shape `ErrorResponse` es consistente con el `ErrorResponse` de MIL/U1
(Q7=A): `error_code`, `message`, `request_id`, `details`.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Cuerpo uniforme para toda respuesta de error del bridge."""

    error_code: str = Field(..., description="Código estable, parseable por el cliente")
    message: str = Field(..., description="Mensaje legible (sin filtrar internals de HANA)")
    request_id: str | None = Field(None, description="Correlación con los logs")
    details: dict[str, Any] | None = Field(None, description="Contexto adicional opcional")


class BridgeError(Exception):
    """Error base del bridge. Mapea a un status HTTP y a un `error_code`.

    Las subclases NO deben incluir información sensible en `message`
    (los detalles técnicos van al log, no a la respuesta).
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str = "Error interno del bridge",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_response(self, request_id: str | None = None) -> ErrorResponse:
        return ErrorResponse(
            error_code=self.error_code,
            message=self.message,
            request_id=request_id,
            details=self.details,
        )


class ValidationError(BridgeError):
    """Input inválido: tabla/columna/operador fuera de whitelist, filtro malformado,
    intento de SQL injection. (Issues #1 y #4 → 400)."""

    status_code = 400
    error_code = "validation_error"


class AuthError(BridgeError):
    """Token ausente o inválido."""

    status_code = 401
    error_code = "unauthorized"


class ForbiddenError(BridgeError):
    """Recurso reconocido pero no permitido para este cliente."""

    status_code = 403
    error_code = "forbidden"


class NotFoundError(BridgeError):
    """Tabla/columna/recurso inexistente."""

    status_code = 404
    error_code = "not_found"


class PoolTimeoutError(BridgeError):
    """No se pudo obtener una conexión del pool dentro del timeout."""

    status_code = 503
    error_code = "pool_exhausted"


class HanaError(BridgeError):
    """Fallo al ejecutar contra HANA (upstream)."""

    status_code = 502
    error_code = "hana_error"
