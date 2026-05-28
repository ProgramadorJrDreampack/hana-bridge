"""Dependencias compartidas: settings, auth, paginación y acceso a servicios.

Los servicios se construyen una vez en el lifespan (`main.create_app`) y viven
en `app.state`; aquí solo se inyectan. Esto materializa la inversión de
dependencias: los routers no instancian pool ni repositorio.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, Query, Request

from config import Settings, get_settings
from core.security import verify_token
from db.whitelist import Whitelist
from services.generic_service import GenericService
from services.production_service import ProductionService
from services.sales_service import SalesService
from services.schema_service import SchemaService


def settings_dep() -> Settings:
    return get_settings()


def verify_auth(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(settings_dep),
) -> None:
    """Valida el Bearer token. Lanza AuthError (401) si falta o es inválido."""
    verify_token(authorization, settings.api_token.get_secret_value())


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int


def pagination_params(
    page: int = Query(1, ge=1, description="Página (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Tamaño de página (máx 100)"),
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


def get_sales_service(request: Request) -> SalesService:
    return request.app.state.sales_service


def get_production_service(request: Request) -> ProductionService:
    return request.app.state.production_service


def get_schema_service(request: Request) -> SchemaService:
    return request.app.state.schema_service


def get_generic_service(request: Request) -> GenericService:
    return request.app.state.generic_service


def get_whitelist(request: Request) -> Whitelist:
    return request.app.state.whitelist
