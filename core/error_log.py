"""Log de errores estructurado: stdout + archivo rotativo.

Centraliza la configuración de logging del bridge. El archivo de errores
(`ERROR_LOG_FILE`) rota para no crecer sin límite y está en .gitignore (`*.log`).
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_CONFIGURED = False
_LOGGER_NAME = "hana_bridge"

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(level: str = "INFO", error_log_file: str = "logs/errors.log") -> None:
    """Configura el logger raíz del bridge. Idempotente."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT)

    # Consola (stdout) — visible en `docker logs`.
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    # Archivo rotativo solo para WARNING+ (el "log de errores").
    try:
        os.makedirs(os.path.dirname(error_log_file) or ".", exist_ok=True)
        file_handler = RotatingFileHandler(
            error_log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Si el filesystem es de solo lectura, seguimos con stdout únicamente.
        logger.warning("No se pudo abrir el archivo de log %s; usando solo stdout", error_log_file)

    _CONFIGURED = True


def get_logger() -> logging.Logger:
    """Devuelve el logger del bridge (configurar antes con `configure_logging`)."""
    return logging.getLogger(_LOGGER_NAME)


def log_error(
    message: str,
    *,
    request_id: str | None = None,
    exc: BaseException | None = None,
    context: dict[str, object] | None = None,
) -> None:
    """Registra un error con correlación de `request_id` y contexto opcional."""
    logger = get_logger()
    suffix = f" | request_id={request_id}" if request_id else ""
    if context:
        suffix += f" | context={context}"
    logger.error("%s%s", message, suffix, exc_info=exc)
