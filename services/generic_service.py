"""Servicio genérico de consulta: el cliente arma su query sobre cualquier
tabla de la whitelist (schema autorizado + tabla introspeccionada).

Cada entrada del cliente pasa por validación dura ANTES de tocar SQL:
  - `schema`     → whitelist.resolve_schema       (lista cerrada)
  - `table`      → whitelist.assert_table         (introspección live)
  - `columns`    → whitelist.assert_columns       (introspección live)
  - `filters`    → operador whitelist + valores parametrizados
  - `order_by`   → columnas validadas + dirección ASC/DESC

Es la implementación canónica del flujo "discover tables → discover columns →
build query": el agente (o un cliente humano) primero llama a `/schema/tables`
y `/schema/columns`, y con eso compone su `/table/{name}?...`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.errors import ValidationError
from db.query_builder import ALLOWED_OPERATORS, Filter, OrderBy, build_select
from db.repository import Repository
from db.whitelist import Whitelist
from models.pagination import PageResponse, build_page


@dataclass(frozen=True)
class _ParsedQuery:
    columns: list[str] | None
    filters: list[Filter]
    order_by: list[OrderBy]


class GenericService:
    def __init__(self, repository: Repository, whitelist: Whitelist) -> None:
        self._repo = repository
        self._whitelist = whitelist

    # ─── API pública ────────────────────────────────────────────────────────
    def query_table(
        self,
        *,
        schema: str | None,
        table: str,
        page: int,
        page_size: int,
        columns_csv: str | None = None,
        filters_json: str | None = None,
        order_by_csv: str,
    ) -> PageResponse:
        schema = self._whitelist.resolve_schema(schema)
        self._whitelist.assert_table(schema, table)

        parsed = self._parse_inputs(columns_csv, filters_json, order_by_csv)

        # Validar contra la introspección viva: columnas seleccionadas, columnas
        # usadas en filtros, columnas usadas en order_by — todas deben existir.
        all_cols_used: list[str] = []
        if parsed.columns:
            all_cols_used.extend(parsed.columns)
        all_cols_used.extend(f.column for f in parsed.filters)
        all_cols_used.extend(o.column for o in parsed.order_by)
        if all_cols_used:
            self._whitelist.assert_columns(schema, table, all_cols_used)

        query = build_select(
            schema=schema,
            table=table,
            columns=parsed.columns,
            order_by=parsed.order_by,
            filters=parsed.filters,
            page=page,
            page_size=page_size,
        )
        data, total = self._repo.fetch_page(query)
        return build_page(data, total, page, page_size)

    # ─── Parsing de los inputs del cliente ──────────────────────────────────
    def _parse_inputs(
        self,
        columns_csv: str | None,
        filters_json: str | None,
        order_by_csv: str,
    ) -> _ParsedQuery:
        return _ParsedQuery(
            columns=self._parse_columns(columns_csv),
            filters=self._parse_filters(filters_json),
            order_by=self._parse_order_by(order_by_csv),
        )

    @staticmethod
    def _parse_columns(csv: str | None) -> list[str] | None:
        if not csv:
            return None
        cols = [c.strip() for c in csv.split(",") if c.strip()]
        return cols or None

    @staticmethod
    def _parse_filters(raw_json: str | None) -> list[Filter]:
        if not raw_json:
            return []
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValidationError("filters: JSON inválido", details={"error": str(exc)}) from exc
        if not isinstance(data, list):
            raise ValidationError("filters: debe ser una lista")
        out: list[Filter] = []
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValidationError(f"filters[{idx}]: debe ser objeto {{column,op,value}}")
            col = item.get("column")
            op = item.get("op")
            if not col or not op:
                raise ValidationError(f"filters[{idx}]: 'column' y 'op' son obligatorios")
            if op not in ALLOWED_OPERATORS:
                raise ValidationError(
                    f"filters[{idx}]: operador no permitido",
                    details={"op": op, "allowed": sorted(ALLOWED_OPERATORS)},
                )
            out.append(Filter(column=col, op=op, value=item.get("value")))
        return out

    @staticmethod
    def _parse_order_by(csv: str) -> list[OrderBy]:
        # order_by es obligatorio: sin él la paginación no es determinista (Issue #2).
        if not csv or not csv.strip():
            raise ValidationError(
                "Se requiere 'order_by' (CSV de columnas, opcional ':DESC'). "
                "Ej: 'DocNum:DESC' o 'DocDate:DESC,DocNum:DESC'"
            )
        out: list[OrderBy] = []
        for item in csv.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                col, direction = item.split(":", 1)
                out.append(OrderBy(column=col.strip(), direction=direction.strip()))
            else:
                out.append(OrderBy(column=item))
        if not out:
            raise ValidationError("'order_by' no puede estar vacío")
        return out
