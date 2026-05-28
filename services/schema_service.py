"""Introspección del catálogo de HANA con cache TTL (Q4=C).

Consulta `SYS.TABLES` y `SYS.TABLE_COLUMNS` de forma parametrizada (el schema y
la tabla van como VALORES, nunca como identificadores concatenados). El cache
evita golpear HANA en cada validación de whitelist.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from config import Settings
from db.repository import Repository

_TABLES_SQL = (
    'SELECT "TABLE_NAME", "COMMENTS" '
    'FROM "SYS"."TABLES" WHERE "SCHEMA_NAME" = ? ORDER BY "TABLE_NAME"'
)
_COLUMNS_SQL = (
    'SELECT "COLUMN_NAME", "DATA_TYPE_NAME", "LENGTH", "IS_NULLABLE", "COMMENTS" '
    'FROM "SYS"."TABLE_COLUMNS" WHERE "SCHEMA_NAME" = ? AND "TABLE_NAME" = ? '
    'ORDER BY "POSITION"'
)


class _TTLCache:
    """Cache simple con expiración por entrada, thread-safe."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if self._ttl and time.monotonic() > expires_at:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, value)


class SchemaService:
    def __init__(self, repository: Repository, settings: Settings) -> None:
        self._repo = repository
        self._settings = settings
        self._cache = _TTLCache(settings.whitelist_cache_ttl_seconds)

    def list_tables(self, schema: str) -> list[dict[str, Any]]:
        cache_key = ("tables", schema)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        rows = self._repo.fetch_all(_TABLES_SQL, [schema])
        self._cache.set(cache_key, rows)
        return rows

    def list_columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        cache_key = ("columns", schema, table)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        rows = self._repo.fetch_all(_COLUMNS_SQL, [schema, table])
        self._cache.set(cache_key, rows)
        return rows

    def table_names(self, schema: str) -> set[str]:
        return {str(r.get("TABLE_NAME")) for r in self.list_tables(schema)}

    def column_names(self, schema: str, table: str) -> set[str]:
        return {str(r.get("COLUMN_NAME")) for r in self.list_columns(schema, table)}
