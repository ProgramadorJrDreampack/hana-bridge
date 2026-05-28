"""Endpoints de producción BEAS."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from models.pagination import PageResponse
from routes.deps import Pagination, get_production_service, pagination_params, verify_auth
from services.production_service import ProductionService

router = APIRouter(tags=["production"], dependencies=[Depends(verify_auth)])


@router.get("/production-orders", response_model=PageResponse)
def get_production_orders(
    schema: str | None = Query(None, description="Esquema (default: el configurado en ALLOWED_SCHEMAS)"),
    status: str | None = Query(None, description="ABGKZ: J=cerrada, N=abierta"),
    pg: Pagination = Depends(pagination_params),
    svc: ProductionService = Depends(get_production_service),
) -> PageResponse:
    return svc.get_production_orders(schema, pg.page, pg.page_size, status)
