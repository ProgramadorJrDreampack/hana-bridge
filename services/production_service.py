"""Lógica de negocio de los endpoints de producción BEAS.

Corrige el Issue #4: el bridge original apuntaba a `"BEAS"."PRODUCTION_ORDER"`
(tabla inexistente). La tabla real de cabecera de órdenes de trabajo es
`BEAS_FTHAUPT`, que vive en la company DB configurada (ver `ALLOWED_SCHEMAS`).

⚠️ Las columnas se tomaron de la documentación oficial BEAS (Boyum IT). Deben
   verificarse en vivo con `/schema/columns?schema=<COMPANY_DB>&table=BEAS_FTHAUPT`
   antes de pasar a producción.
"""
from __future__ import annotations

from db.query_builder import Filter, OrderBy, build_select
from db.repository import Repository
from db.whitelist import Whitelist
from models.pagination import PageResponse, build_page

# Tabla real (no "PRODUCTION_ORDER"). AUFTRAG=nº orden, ABGKZ=cerrada (J/N).
_PRODUCTION_TABLE = "BEAS_FTHAUPT"
_PRODUCTION_COLUMNS = [
    "AUFTRAG", "ItemCode", "ABGKZ", "ANFZEIT", "ENDZEIT", "BELDAT", "LFGDAT",
    "PLANNEDHOURS", "PLANNEDCOSTS", "KND_ID", "KNDNAME", "PROJECTSTATE", "PRIOR_ID",
]


class ProductionService:
    def __init__(self, repository: Repository, whitelist: Whitelist) -> None:
        self._repo = repository
        self._whitelist = whitelist

    def get_production_orders(
        self,
        schema: str | None,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> PageResponse:
        schema = self._whitelist.resolve_schema(schema)
        filters = []
        if status:
            # ABGKZ: 'J' = cerrada, 'N' = abierta.
            filters.append(Filter("ABGKZ", "eq", status))
        query = build_select(
            schema=schema,
            table=_PRODUCTION_TABLE,
            columns=_PRODUCTION_COLUMNS,
            order_by=[OrderBy("AUFTRAG", "DESC")],
            filters=filters,
            page=page,
            page_size=page_size,
        )
        data, total = self._repo.fetch_page(query)
        return build_page(data, total, page, page_size)
