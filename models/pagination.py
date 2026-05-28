"""Modelos de paginación. Mantiene el contrato externo `page/page_size` (Q3=A)."""
from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PageResponse(BaseModel):
    data: list[dict[str, Any]]
    pagination: PageMeta


def build_page(
    data: list[dict[str, Any]], total: int, page: int, page_size: int
) -> PageResponse:
    """Arma la respuesta paginada con su metadata derivada."""
    total_pages = math.ceil(total / page_size) if page_size and total else 0
    return PageResponse(
        data=data,
        pagination=PageMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )
