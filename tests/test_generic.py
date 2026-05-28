"""Tests del endpoint genérico /table/{name}: parseo seguro + integración con whitelist."""
import pytest

from core.errors import NotFoundError, ValidationError
from services.generic_service import GenericService


# ─── Fakes mínimos para aislar la capa de parseo ─────────────────────────────
class _FakeSchemaService:
    def table_names(self, schema):
        return {"OINV", "OITM", "ORDR"}

    def column_names(self, schema, table):
        return {
            "OINV": {"DocNum", "CardCode", "CardName", "DocDate", "DocTotal", "DocStatus"},
            "OITM": {"ItemCode", "ItemName", "OnHand"},
        }[table]


class _FakeWhitelist:
    def resolve_schema(self, schema):
        return schema or "MYCOMPANY_DB"

    def assert_table(self, schema, table):
        if table not in {"OINV", "OITM", "ORDR"}:
            raise NotFoundError("tabla no existe", details={"table": table})

    def assert_columns(self, schema, table, columns):
        valid = _FakeSchemaService().column_names(schema, table)
        invalid = [c for c in columns if c not in valid]
        if invalid:
            raise ValidationError("cols inválidas", details={"invalid": invalid})


class _RepoStub:
    """Reemplaza repository: devuelve la BuiltQuery para inspección + datos vacíos."""

    def __init__(self):
        self.last_query = None

    def fetch_page(self, query):
        self.last_query = query
        return [], 0


# ─── parseo de columns ───────────────────────────────────────────────────────
def test_columns_none_significa_todas():
    assert GenericService._parse_columns(None) is None
    assert GenericService._parse_columns("") is None


def test_columns_csv_se_parte_y_limpia():
    assert GenericService._parse_columns("DocNum, CardCode , DocTotal") == [
        "DocNum",
        "CardCode",
        "DocTotal",
    ]


# ─── parseo de filters ───────────────────────────────────────────────────────
def test_filters_none_es_lista_vacia():
    assert GenericService._parse_filters(None) == []


def test_filters_json_invalido_rechazado():
    with pytest.raises(ValidationError):
        GenericService._parse_filters("{no es json}")


def test_filters_debe_ser_lista():
    with pytest.raises(ValidationError):
        GenericService._parse_filters('{"column":"x","op":"eq","value":1}')


def test_filters_operador_no_permitido_rechazado():
    with pytest.raises(ValidationError):
        GenericService._parse_filters(
            '[{"column":"DocStatus","op":"OR 1=1 --","value":"O"}]'
        )


def test_filters_falta_column_o_op_rechazado():
    with pytest.raises(ValidationError):
        GenericService._parse_filters('[{"op":"eq","value":"O"}]')
    with pytest.raises(ValidationError):
        GenericService._parse_filters('[{"column":"DocStatus","value":"O"}]')


def test_filters_ok_se_traducen_a_Filter():
    out = GenericService._parse_filters(
        '[{"column":"DocStatus","op":"eq","value":"O"},'
        ' {"column":"DocDate","op":"gte","value":"2026-01-01"}]'
    )
    assert len(out) == 2
    assert out[0].column == "DocStatus" and out[0].op == "eq" and out[0].value == "O"
    assert out[1].op == "gte"


# ─── parseo de order_by ──────────────────────────────────────────────────────
def test_order_by_es_obligatorio():
    with pytest.raises(ValidationError):
        GenericService._parse_order_by("")
    with pytest.raises(ValidationError):
        GenericService._parse_order_by("   ")


def test_order_by_csv_con_direccion():
    out = GenericService._parse_order_by("DocDate:DESC, DocNum:DESC")
    assert [(o.column, o.direction) for o in out] == [("DocDate", "DESC"), ("DocNum", "DESC")]


def test_order_by_default_asc_cuando_no_se_indica():
    out = GenericService._parse_order_by("DocNum")
    assert out[0].column == "DocNum" and out[0].direction == "ASC"


# ─── Integración: query_table arma SQL parametrizado ─────────────────────────
def test_query_table_arma_sql_seguro_y_parametrizado():
    repo = _RepoStub()
    svc = GenericService(repo, _FakeWhitelist())

    svc.query_table(
        schema=None,
        table="OINV",
        page=1,
        page_size=10,
        columns_csv="DocNum,CardName,DocTotal",
        filters_json='[{"column":"DocStatus","op":"eq","value":"O"}]',
        order_by_csv="DocNum:DESC",
    )

    q = repo.last_query
    assert q is not None
    # Identificadores entrecomillados, valor como parámetro
    assert q.sql.startswith('SELECT "DocNum", "CardName", "DocTotal" FROM "MYCOMPANY_DB"."OINV"')
    assert 'WHERE "DocStatus" = ?' in q.sql
    assert q.params == ["O"]
    assert "LIMIT 10 OFFSET 0" in q.sql


def test_query_table_rechaza_tabla_fuera_de_whitelist():
    svc = GenericService(_RepoStub(), _FakeWhitelist())
    with pytest.raises(NotFoundError):
        svc.query_table(
            schema=None, table="SYSUSERS",
            page=1, page_size=10,
            order_by_csv="x",
        )


def test_query_table_rechaza_columna_inexistente():
    svc = GenericService(_RepoStub(), _FakeWhitelist())
    with pytest.raises(ValidationError):
        svc.query_table(
            schema=None, table="OINV",
            page=1, page_size=10,
            columns_csv="DocNum,EvilCol",
            order_by_csv="DocNum:DESC",
        )


def test_query_table_rechaza_columna_de_filtro_inexistente():
    svc = GenericService(_RepoStub(), _FakeWhitelist())
    with pytest.raises(ValidationError):
        svc.query_table(
            schema=None, table="OINV",
            page=1, page_size=10,
            filters_json='[{"column":"NoExiste","op":"eq","value":"x"}]',
            order_by_csv="DocNum:DESC",
        )
