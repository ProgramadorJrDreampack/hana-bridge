"""Constructor de SQL seguro (Issue #1, Q8=A).

Reglas inviolables:
  1. Todo identificador (schema, tabla, columna) se valida contra un regex
     estricto y se entrecomilla. Nunca se interpola input crudo como identificador.
  2. Todo VALOR va como parámetro (`?`), nunca concatenado al SQL.
  3. Los operadores provienen de una whitelist cerrada.
  4. La paginación usa `LIMIT/OFFSET` con `page/page_size` validados como enteros
     y un `ORDER BY` estable (por PK) → determinista, sin duplicados (Issue #2).

`ColumnRef` permite comparar una columna contra otra (ej. `OnHand <= MinLevel`)
de forma segura: ambos lados son identificadores validados, sin parámetros.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.errors import ValidationError

# Identificador SQL válido: letra/underscore inicial, luego alfanumérico/underscore.
# Cubre columnas SAP B1 con mayúsculas/minúsculas ("ItemCode", "DocNum", "AUFTRAG").
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Operadores binarios permitidos → símbolo SQL. `in` y `between` se tratan aparte.
_OP_SYMBOLS: dict[str, str] = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
}
ALLOWED_OPERATORS = set(_OP_SYMBOLS) | {"in", "between"}

_DIRECTIONS = {"ASC", "DESC"}


@dataclass(frozen=True)
class ColumnRef:
    """Referencia a otra columna (para comparaciones columna-vs-columna)."""

    column: str


@dataclass(frozen=True)
class Filter:
    """Un predicado de WHERE: columna, operador (whitelist) y valor(es).

    `value` puede ser un literal (→ parámetro), una lista (para `in`/`between`)
    o un `ColumnRef` (→ comparación con otra columna, sin parámetro).
    """

    column: str
    op: str
    value: Any


@dataclass(frozen=True)
class OrderBy:
    """Una columna de ordenamiento con dirección."""

    column: str
    direction: str = "ASC"


def quote_ident(name: str) -> str:
    """Valida un identificador y lo entrecomilla. Lanza ValidationError si es inválido."""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValidationError("Identificador inválido", details={"identifier": str(name)})
    return f'"{name}"'


def qualified_name(schema: str, table: str) -> str:
    """`"SCHEMA"."TABLE"` con ambos identificadores validados."""
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def _render_binary(col: str, op: str, value: Any, params: list[Any]) -> str:
    symbol = _OP_SYMBOLS[op]
    if isinstance(value, ColumnRef):
        # Comparación columna-vs-columna: identificador validado, sin parámetro.
        if op == "like":
            raise ValidationError("LIKE no admite comparación entre columnas")
        return f"{col} {symbol} {quote_ident(value.column)}"
    params.append(value)
    return f"{col} {symbol} ?"


def _build_where(filters: list[Filter]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for flt in filters:
        col = quote_ident(flt.column)
        if flt.op == "in":
            values = list(flt.value) if isinstance(flt.value, (list, tuple)) else None
            if not values:
                raise ValidationError("El operador 'in' requiere una lista no vacía")
            placeholders = ", ".join("?" for _ in values)
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(values)
        elif flt.op == "between":
            if not (isinstance(flt.value, (list, tuple)) and len(flt.value) == 2):
                raise ValidationError("El operador 'between' requiere [min, max]")
            clauses.append(f"{col} BETWEEN ? AND ?")
            params.extend(flt.value)
        elif flt.op in _OP_SYMBOLS:
            clauses.append(_render_binary(col, flt.op, flt.value, params))
        else:
            raise ValidationError("Operador no permitido", details={"operator": flt.op})
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def _build_order(order_by: list[OrderBy]) -> str:
    if not order_by:
        # Sin ORDER BY la paginación no es determinista (Issue #2).
        raise ValidationError("Se requiere al menos una columna de ordenamiento")
    parts = []
    for ob in order_by:
        direction = ob.direction.upper()
        if direction not in _DIRECTIONS:
            raise ValidationError("Dirección de orden inválida", details={"dir": ob.direction})
        parts.append(f"{quote_ident(ob.column)} {direction}")
    return f" ORDER BY {', '.join(parts)}"


@dataclass(frozen=True)
class BuiltQuery:
    """SQL paginado + SQL de conteo, con sus parámetros."""

    sql: str
    params: list[Any]
    count_sql: str
    count_params: list[Any]


def build_select(
    *,
    schema: str,
    table: str,
    columns: list[str] | None,
    order_by: list[OrderBy],
    filters: list[Filter] | None = None,
    page: int,
    page_size: int,
) -> BuiltQuery:
    """Construye un SELECT paginado seguro + su conteo.

    `page`/`page_size` deben ser enteros ya validados (vienen de Pydantic). Se
    incrustan como literales enteros: son seguros y HANA no siempre acepta
    placeholders en LIMIT/OFFSET.
    """
    if not isinstance(page, int) or not isinstance(page_size, int) or page < 1 or page_size < 1:
        raise ValidationError("Parámetros de paginación inválidos")

    filters = filters or []
    select_cols = ", ".join(quote_ident(c) for c in columns) if columns else "*"
    target = qualified_name(schema, table)
    where_sql, params = _build_where(filters)
    order_sql = _build_order(order_by)
    offset = (page - 1) * page_size

    sql = f"SELECT {select_cols} FROM {target}{where_sql}{order_sql} LIMIT {page_size} OFFSET {offset}"
    count_sql = f"SELECT COUNT(*) FROM {target}{where_sql}"
    return BuiltQuery(sql=sql, params=params, count_sql=count_sql, count_params=list(params))
