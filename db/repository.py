"""Repositorio: ejecuta SQL parametrizado vía el pool y mapea filas a dicts.

Es la única capa que habla con el cursor de hdbcli. Normaliza cualquier fallo
de HANA a `HanaError` (502) sin filtrar el mensaje crudo al cliente (va al log).
"""
from __future__ import annotations

from typing import Any

from core.error_log import log_error
from core.errors import HanaError
from db.pool import HanaConnectionPool
from db.query_builder import BuiltQuery


class Repository:
    def __init__(self, pool: HanaConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _rows_to_dicts(cursor: Any) -> list[dict[str, Any]]:
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def fetch_all(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Ejecuta un SELECT y devuelve todas las filas como dicts."""
        with self._pool.acquire() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params or [])
                return self._rows_to_dicts(cursor)
            except Exception as exc:  # noqa: BLE001
                log_error("Fallo ejecutando query en HANA", exc=exc, context={"sql": sql})
                raise HanaError("Error consultando HANA") from exc
            finally:
                cursor.close()

    def fetch_page(self, query: BuiltQuery) -> tuple[list[dict[str, Any]], int]:
        """Ejecuta conteo + página en la MISMA conexión. Devuelve (filas, total)."""
        with self._pool.acquire() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query.count_sql, query.count_params)
                total = int(cursor.fetchone()[0])
                cursor.execute(query.sql, query.params)
                data = self._rows_to_dicts(cursor)
                return data, total
            except Exception as exc:  # noqa: BLE001
                log_error("Fallo en query paginada", exc=exc, context={"sql": query.sql})
                raise HanaError("Error consultando HANA") from exc
            finally:
                cursor.close()
