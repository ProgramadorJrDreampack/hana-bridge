"""Respuestas de los endpoints de introspección de esquema."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TablesResponse(BaseModel):
    schema_name: str
    tables: list[dict[str, Any]]
    total: int


class ColumnsResponse(BaseModel):
    schema_name: str
    table: str
    columns: list[dict[str, Any]]
