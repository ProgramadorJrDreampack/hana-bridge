"""Tests del query builder, con foco en NEGATIVOS de SQL injection (Issue #1)."""
import pytest

from core.errors import ValidationError
from db.query_builder import ColumnRef, Filter, OrderBy, build_select, quote_ident


def test_quote_ident_valido():
    assert quote_ident("ItemCode") == '"ItemCode"'
    assert quote_ident("AUFTRAG") == '"AUFTRAG"'


@pytest.mark.parametrize(
    "evil",
    [
        "OITM; DROP TABLE x",
        'a" OR "1"="1',
        "a-b",
        "1col",
        "co l",
        "OITM--",
        "",
        "tab;",
        "../etc",
    ],
)
def test_quote_ident_rechaza_injection(evil):
    with pytest.raises(ValidationError):
        quote_ident(evil)


def test_build_select_parametriza_valores():
    q = build_select(
        schema="MYCOMPANY_DB",
        table="OITM",
        columns=["ItemCode", "OnHand"],
        order_by=[OrderBy("ItemCode")],
        filters=[Filter("ItemName", "like", "%tornillo%")],
        page=2,
        page_size=10,
    )
    assert q.sql.startswith('SELECT "ItemCode", "OnHand" FROM "MYCOMPANY_DB"."OITM"')
    assert 'WHERE "ItemName" LIKE ?' in q.sql
    assert 'ORDER BY "ItemCode" ASC' in q.sql
    assert "LIMIT 10 OFFSET 10" in q.sql
    assert q.params == ["%tornillo%"]  # el valor NO se concatena al SQL


def test_build_select_rechaza_columna_maliciosa():
    with pytest.raises(ValidationError):
        build_select(
            schema="S", table="OITM", columns=['x"; DROP TABLE y; --'],
            order_by=[OrderBy("ItemCode")], page=1, page_size=10,
        )


def test_build_select_exige_order_by():
    with pytest.raises(ValidationError):
        build_select(schema="S", table="OITM", columns=None, order_by=[], page=1, page_size=10)


def test_operador_in():
    q = build_select(
        schema="S", table="T", columns=None, order_by=[OrderBy("id")],
        filters=[Filter("c", "in", [1, 2, 3])], page=1, page_size=5,
    )
    assert "IN (?, ?, ?)" in q.sql
    assert q.params == [1, 2, 3]


def test_operador_in_vacio_rechazado():
    with pytest.raises(ValidationError):
        build_select(
            schema="S", table="T", columns=None, order_by=[OrderBy("id")],
            filters=[Filter("c", "in", [])], page=1, page_size=5,
        )


def test_operador_between():
    q = build_select(
        schema="S", table="T", columns=None, order_by=[OrderBy("id")],
        filters=[Filter("d", "between", ["2026-01-01", "2026-12-31"])], page=1, page_size=5,
    )
    assert "BETWEEN ? AND ?" in q.sql
    assert q.params == ["2026-01-01", "2026-12-31"]


def test_operador_invalido_rechazado():
    with pytest.raises(ValidationError):
        build_select(
            schema="S", table="T", columns=None, order_by=[OrderBy("id")],
            filters=[Filter("c", "OR 1=1; --", 1)], page=1, page_size=5,
        )


def test_columnref_no_genera_parametro():
    q = build_select(
        schema="S", table="OITM", columns=None, order_by=[OrderBy("ItemCode")],
        filters=[Filter("OnHand", "lte", ColumnRef("MinLevel"))], page=1, page_size=5,
    )
    assert '"OnHand" <= "MinLevel"' in q.sql
    assert q.params == []


def test_paginacion_offset():
    q = build_select(
        schema="S", table="T", columns=None, order_by=[OrderBy("id")],
        page=3, page_size=25,
    )
    assert "LIMIT 25 OFFSET 50" in q.sql
