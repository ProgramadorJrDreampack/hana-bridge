"""Introspección de esquema: listar tablas y columnas.

`/schema/columns` está definido UNA sola vez (corrige Issue #3, que tenía la
ruta duplicada).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from db.whitelist import Whitelist
from models.schema_models import ColumnsResponse, TablesResponse
from routes.deps import get_schema_service, get_whitelist, verify_auth
from services.schema_service import SchemaService

router = APIRouter(prefix="/schema", tags=["schema"], dependencies=[Depends(verify_auth)])


@router.get("/tables", response_model=TablesResponse)
def get_tables(
    schema: str | None = Query(None),
    svc: SchemaService = Depends(get_schema_service),
    whitelist: Whitelist = Depends(get_whitelist),
) -> TablesResponse:
    schema = whitelist.resolve_schema(schema)
    rows = svc.list_tables(schema)
    return TablesResponse(schema_name=schema, tables=rows, total=len(rows))


@router.get("/columns", response_model=ColumnsResponse)
def get_columns(
    table: str = Query(..., description="Nombre de la tabla"),
    schema: str | None = Query(None),
    svc: SchemaService = Depends(get_schema_service),
    whitelist: Whitelist = Depends(get_whitelist),
) -> ColumnsResponse:
    schema = whitelist.resolve_schema(schema)
    whitelist.assert_table(schema, table)
    rows = svc.list_columns(schema, table)
    return ColumnsResponse(schema_name=schema, table=table, columns=rows)
