"""Endpoint genérico `/table/{table}` — consulta segura sobre cualquier tabla
de la whitelist.

Patrón de uso (humano o agente):
  1) GET /schema/tables                          → ver tablas disponibles
  2) GET /schema/columns?table=OINV              → ver columnas de la tabla
  3) GET /table/OINV?columns=...&filters=...&order_by=...    → consultar

Toda input pasa por validación (schema/tabla/columnas contra introspección
live; operador contra whitelist; valores como parámetros bind). El cliente
NO puede construir SQL libre — solo combinaciones válidas.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from models.pagination import PageResponse
from routes.deps import (
    Pagination,
    get_generic_service,
    pagination_params,
    verify_auth,
)
from services.generic_service import GenericService

router = APIRouter(tags=["generic"], dependencies=[Depends(verify_auth)])


@router.get("/table/{table}", response_model=PageResponse)
def query_table(
    table: str,
    schema: str | None = Query(None, description="Schema (default: el configurado)"),
    columns: str | None = Query(
        None,
        description="CSV de columnas a devolver. Vacío = todas. Ej: 'DocNum,CardName,DocTotal'",
    ),
    filters: str | None = Query(
        None,
        description=(
            "JSON con la lista de filtros. Operadores permitidos: "
            "eq, ne, gt, gte, lt, lte, like, in, between. "
            'Ej: \'[{"column":"DocStatus","op":"eq","value":"O"},'
            '{"column":"DocDate","op":"gte","value":"2026-01-01"}]\''
        ),
    ),
    order_by: str = Query(
        ...,
        description=(
            "REQUERIDO. CSV de columnas, opcionalmente con ':ASC'/':DESC'. "
            "Garantiza paginación determinista. Ej: 'DocNum:DESC' o 'DocDate:DESC,DocNum:DESC'"
        ),
    ),
    pg: Pagination = Depends(pagination_params),
    svc: GenericService = Depends(get_generic_service),
) -> PageResponse:
    return svc.query_table(
        schema=schema,
        table=table,
        page=pg.page,
        page_size=pg.page_size,
        columns_csv=columns,
        filters_json=filters,
        order_by_csv=order_by,
    )
