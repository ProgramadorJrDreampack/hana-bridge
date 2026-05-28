"""Configuración central del HANA Bridge.

Todas las variables de entorno se declaran aquí (fuente única de verdad) y se
cargan desde `.env`. NINGÚN secreto tiene valor por defecto: si falta, la app
falla al arrancar (fail-fast) en vez de usar credenciales embebidas.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Settings tipados, cargados desde el entorno / archivo `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Autenticación del bridge ───────────────────────────────────────────
    api_token: SecretStr = Field(..., description="Bearer token requerido por los clientes")

    # ─── Conexión a SAP HANA ────────────────────────────────────────────────
    hana_host: str = Field(..., description="Host/IP de HANA")
    hana_port: int = Field(30015, ge=1, le=65535)
    hana_user: str = Field(..., description="Usuario read-only de HANA")
    hana_password: SecretStr = Field(..., description="Password del usuario HANA")
    hana_encrypt: bool = Field(True, description="Cifrar la conexión TLS")
    hana_ssl_validate: bool = Field(
        False, description="Validar el certificado del servidor HANA"
    )

    # ─── Pool de conexiones ─────────────────────────────────────────────────
    pool_size: int = Field(5, ge=1, le=50, description="Máximo de conexiones simultáneas")
    pool_acquire_timeout_seconds: float = Field(
        10.0, gt=0, description="Espera máx. para obtener una conexión del pool"
    )

    # ─── Whitelist y consultas ──────────────────────────────────────────────
    # NoDecode: evita que pydantic-settings intente json.loads sobre el valor;
    # el validador `_split_csv` lo parte por comas.
    allowed_schemas: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["MYCOMPANY_DB"],
        description="Esquemas HANA autorizados (CSV en el .env)",
    )
    default_schema: str = Field(
        "MYCOMPANY_DB", description="Esquema por defecto si el cliente no envía uno"
    )
    whitelist_cache_ttl_seconds: int = Field(
        300, ge=0, description="TTL del cache de tablas/columnas para la whitelist"
    )
    max_page_size: int = Field(100, ge=1, le=1000)
    default_page_size: int = Field(20, ge=1)

    # ─── Observabilidad ─────────────────────────────────────────────────────
    log_level: str = Field("INFO", description="DEBUG | INFO | WARNING | ERROR")
    error_log_file: str = Field(
        "logs/errors.log", description="Ruta del log rotativo de errores"
    )
    app_env: str = Field("development", description="development | production")

    @field_validator("allowed_schemas", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Permite definir ALLOWED_SCHEMAS como CSV en el `.env`."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"log_level inválido: {value}")
        return normalized

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de Settings (singleton de proceso)."""
    return Settings()  # type: ignore[call-arg]  # valores vienen del entorno
