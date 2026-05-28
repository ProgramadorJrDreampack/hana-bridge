"""Lógica de negocio de los endpoints SAP B1 (items, orders, compras, stock).

Las tablas y columnas son constantes confiables (no provienen del cliente). El
único input de identificador que entra es `schema`, que se valida contra la
whitelist. Los filtros del cliente (search, warehouse, status) van como VALORES
parametrizados.
"""
from __future__ import annotations

from db.query_builder import ColumnRef, Filter, OrderBy, build_select
from db.repository import Repository
from db.whitelist import Whitelist
from models.pagination import PageResponse, build_page

_ITEM_COLUMNS = ["ItemCode", "ItemName", "OnHand", "OnOrder", "IsCommited", "DfltWH", "UpdateDate"]
_ORDER_COLUMNS = [
    "DocNum", "CardCode", "CardName", "DocDate", "DocDueDate",
    "DocTotal", "DocCur", "DocStatus", "Comments",
]
_STOCK_COLUMNS = ["ItemCode", "ItemName", "OnHand", "MinLevel", "DfltWH"]
# Facturas de deudores (OINV) — subset razonable; el cliente puede usar /table/OINV
# si necesita más columnas o filtros ad-hoc.
_INVOICE_COLUMNS = [
    "DocEntry", "DocNum", "CardCode", "CardName", "DocDate", "DocDueDate",
    "DocTotal", "DocCur", "DocStatus", "PaidToDate", "VatSum", "Comments",
]


class SalesService:
    def __init__(self, repository: Repository, whitelist: Whitelist) -> None:
        self._repo = repository
        self._whitelist = whitelist

    def _run(self, *, schema, table, columns, order_by, filters, page, page_size) -> PageResponse:
        query = build_select(
            schema=schema,
            table=table,
            columns=columns,
            order_by=order_by,
            filters=filters,
            page=page,
            page_size=page_size,
        )
        data, total = self._repo.fetch_page(query)
        return build_page(data, total, page, page_size)

    def get_items(
        self,
        schema: str | None,
        page: int,
        page_size: int,
        search: str | None = None,
        warehouse: str | None = None,
    ) -> PageResponse:
        schema = self._whitelist.resolve_schema(schema)
        filters = [Filter("InvntItem", "eq", "Y")]
        if search:
            filters.append(Filter("ItemName", "like", f"%{search}%"))
        if warehouse:
            filters.append(Filter("DfltWH", "eq", warehouse))
        return self._run(
            schema=schema, table="OITM", columns=_ITEM_COLUMNS,
            order_by=[OrderBy("ItemCode", "ASC")], filters=filters,
            page=page, page_size=page_size,
        )

    def get_orders(self, schema: str | None, page: int, page_size: int, status: str = "O") -> PageResponse:
        schema = self._whitelist.resolve_schema(schema)
        return self._run(
            schema=schema, table="ORDR", columns=_ORDER_COLUMNS,
            order_by=[OrderBy("DocNum", "DESC")],
            filters=[Filter("DocStatus", "eq", status)],
            page=page, page_size=page_size,
        )

    def get_purchase_orders(
        self, schema: str | None, page: int, page_size: int, status: str = "O"
    ) -> PageResponse:
        schema = self._whitelist.resolve_schema(schema)
        return self._run(
            schema=schema, table="OPOR", columns=_ORDER_COLUMNS,
            order_by=[OrderBy("DocNum", "DESC")],
            filters=[Filter("DocStatus", "eq", status)],
            page=page, page_size=page_size,
        )

    def get_invoices(
        self,
        schema: str | None,
        page: int,
        page_size: int,
        status: str | None = None,
        customer: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> PageResponse:
        """Facturas de deudores (OINV) — el equivalente de /orders pero del módulo de ventas/AR."""
        schema = self._whitelist.resolve_schema(schema)
        filters = []
        if status:
            filters.append(Filter("DocStatus", "eq", status))
        if customer:
            filters.append(Filter("CardCode", "eq", customer))
        if date_from and date_to:
            filters.append(Filter("DocDate", "between", [date_from, date_to]))
        elif date_from:
            filters.append(Filter("DocDate", "gte", date_from))
        elif date_to:
            filters.append(Filter("DocDate", "lte", date_to))
        return self._run(
            schema=schema, table="OINV", columns=_INVOICE_COLUMNS,
            order_by=[OrderBy("DocNum", "DESC")],
            filters=filters, page=page, page_size=page_size,
        )

    def get_critical_stock(self, schema: str | None, page: int, page_size: int) -> PageResponse:
        schema = self._whitelist.resolve_schema(schema)
        # OnHand <= MinLevel: comparación columna-vs-columna (segura, sin parámetro).
        filters = [
            Filter("InvntItem", "eq", "Y"),
            Filter("OnHand", "lte", ColumnRef("MinLevel")),
        ]
        return self._run(
            schema=schema, table="OITM", columns=_STOCK_COLUMNS,
            # Orden secundario por ItemCode → paginación determinista (Issue #2).
            order_by=[OrderBy("OnHand", "ASC"), OrderBy("ItemCode", "ASC")],
            filters=filters, page=page, page_size=page_size,
        )
