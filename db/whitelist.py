"""Whitelist de esquemas / tablas / columnas (Issues #1 y #4, Q4=C, Q5).

- `validate_schema`: el `schema` recibido debe estar en `ALLOWED_SCHEMAS`
  (resuelve Issue #4: el param ya no se ignora). Sin schema → usa el default.
- `assert_table` / `assert_columns`: validan contra la introspección en vivo
  (cacheada) del SchemaService. Usados por `/schema/columns` y por futuros
  endpoints genéricos `/table/{name}`.
"""
from __future__ import annotations

from config import Settings
from core.errors import NotFoundError, ValidationError
from db.query_builder import quote_ident
from services.schema_service import SchemaService


class Whitelist:
    def __init__(self, settings: Settings, schema_service: SchemaService) -> None:
        self._settings = settings
        self._schema_service = schema_service

    def resolve_schema(self, schema: str | None) -> str:
        """Devuelve un schema autorizado (o el default) o lanza ValidationError."""
        candidate = (schema or self._settings.default_schema).strip()
        quote_ident(candidate)  # valida forma del identificador (anti-injection)
        if candidate not in self._settings.allowed_schemas:
            raise ValidationError(
                "Esquema no autorizado",
                details={"schema": candidate, "allowed": self._settings.allowed_schemas},
            )
        return candidate

    def assert_table(self, schema: str, table: str) -> None:
        quote_ident(table)
        if table not in self._schema_service.table_names(schema):
            raise NotFoundError(
                "Tabla inexistente o no visible", details={"schema": schema, "table": table}
            )

    def assert_columns(self, schema: str, table: str, columns: list[str]) -> None:
        available = self._schema_service.column_names(schema, table)
        invalid = [c for c in columns if c not in available]
        if invalid:
            raise ValidationError(
                "Columnas no válidas para la tabla",
                details={"schema": schema, "table": table, "invalid": invalid},
            )
