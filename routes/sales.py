"""Endpoints SAP B1: items, órdenes de venta/compra, stock crítico."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from models.pagination import PageResponse
from routes.deps import Pagination, get_sales_service, pagination_params, verify_auth
from services.sales_service import SalesService

router = APIRouter(tags=["sales"], dependencies=[Depends(verify_auth)])


@router.get("/items", response_model=PageResponse)
def get_items(
    schema: str | None = Query(None, description="Esquema SAP (default: el configurado)"),
    search: str | None = Query(None, description="Filtro por nombre de artículo"),
    warehouse: str | None = Query(None, description="Filtro por almacén por defecto"),
    pg: Pagination = Depends(pagination_params),
    svc: SalesService = Depends(get_sales_service),
) -> PageResponse:
    return svc.get_items(schema, pg.page, pg.page_size, search, warehouse)


@router.get("/orders", response_model=PageResponse)
def get_orders(
    schema: str | None = Query(None),
    status: str = Query("O", description="O=Abierta, C=Cerrada"),
    pg: Pagination = Depends(pagination_params),
    svc: SalesService = Depends(get_sales_service),
) -> PageResponse:
    return svc.get_orders(schema, pg.page, pg.page_size, status)


@router.get("/purchase-orders", response_model=PageResponse)
def get_purchase_orders(
    schema: str | None = Query(None),
    status: str = Query("O"),
    pg: Pagination = Depends(pagination_params),
    svc: SalesService = Depends(get_sales_service),
) -> PageResponse:
    return svc.get_purchase_orders(schema, pg.page, pg.page_size, status)


@router.get("/invoices", response_model=PageResponse)
def get_invoices(
    schema: str | None = Query(None),
    status: str | None = Query(None, description="O=abierta, C=cerrada/pagada"),
    customer: str | None = Query(None, description="CardCode del cliente"),
    date_from: str | None = Query(None, description="Fecha desde (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Fecha hasta (YYYY-MM-DD)"),
    pg: Pagination = Depends(pagination_params),
    svc: SalesService = Depends(get_sales_service),
) -> PageResponse:
    """Facturas de deudores (OINV)."""
    return svc.get_invoices(schema, pg.page, pg.page_size, status, customer, date_from, date_to)


@router.get("/stock/critical", response_model=PageResponse)
def get_critical_stock(
    schema: str | None = Query(None),
    pg: Pagination = Depends(pagination_params),
    svc: SalesService = Depends(get_sales_service),
) -> PageResponse:
    return svc.get_critical_stock(schema, pg.page, pg.page_size)
