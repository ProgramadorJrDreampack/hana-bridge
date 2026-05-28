"""Exception handlers de FastAPI → respuesta `ErrorResponse` uniforme.

Toda excepción se traduce a un JSON con el mismo shape y se registra en el
log de errores con su `request_id`. Nunca se filtran trazas internas de HANA
al cliente.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.error_log import log_error
from core.errors import BridgeError, ErrorResponse, ValidationError


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los handlers en la app FastAPI."""

    @app.exception_handler(BridgeError)
    async def _bridge_error_handler(request: Request, exc: BridgeError) -> JSONResponse:
        request_id = _request_id(request)
        # Solo registramos 5xx (errores nuestros / upstream); los 4xx son del cliente.
        if exc.status_code >= 500:
            log_error(
                f"{exc.error_code}: {exc.message}",
                request_id=request_id,
                exc=exc,
                context={"path": request.url.path},
            )
        body = exc.to_response(request_id=request_id)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _request_id(request)
        body = ValidationError(
            "Parámetros de la petición inválidos",
            details={"errors": exc.errors()},
        ).to_response(request_id=request_id)
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        log_error(
            "Excepción no controlada",
            request_id=request_id,
            exc=exc,
            context={"path": request.url.path},
        )
        body = ErrorResponse(
            error_code="internal_error",
            message="Error interno del bridge",
            request_id=request_id,
        )
        return JSONResponse(status_code=500, content=body.model_dump())
