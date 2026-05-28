"""Tests de la whitelist de esquemas / tablas (Issues #1 y #4)."""
import pytest

from config import Settings
from core.errors import NotFoundError, ValidationError
from db.whitelist import Whitelist


class FakeSchemaService:
    def table_names(self, schema):
        return {"OITM", "ORDR", "BEAS_FTHAUPT"}

    def column_names(self, schema, table):
        return {"ItemCode", "OnHand", "MinLevel"}


def _settings():
    return Settings(
        api_token="t",
        hana_host="h",
        hana_user="u",
        hana_password="p",
        allowed_schemas=["MYCOMPANY_DB"],
        default_schema="MYCOMPANY_DB",
    )


def test_resolve_usa_default():
    wl = Whitelist(_settings(), FakeSchemaService())
    assert wl.resolve_schema(None) == "MYCOMPANY_DB"


def test_resolve_acepta_autorizado():
    wl = Whitelist(_settings(), FakeSchemaService())
    assert wl.resolve_schema("MYCOMPANY_DB") == "MYCOMPANY_DB"


def test_resolve_rechaza_no_autorizado():
    wl = Whitelist(_settings(), FakeSchemaService())
    with pytest.raises(ValidationError):
        wl.resolve_schema("SYS")


def test_resolve_rechaza_injection():
    wl = Whitelist(_settings(), FakeSchemaService())
    with pytest.raises(ValidationError):
        wl.resolve_schema('MYCOMPANY_DB"; DROP TABLE x; --')


def test_assert_table_existente():
    wl = Whitelist(_settings(), FakeSchemaService())
    wl.assert_table("MYCOMPANY_DB", "BEAS_FTHAUPT")  # no levanta


def test_assert_table_inexistente():
    wl = Whitelist(_settings(), FakeSchemaService())
    with pytest.raises(NotFoundError):
        wl.assert_table("MYCOMPANY_DB", "NO_EXISTE")


def test_assert_columns_invalidas():
    wl = Whitelist(_settings(), FakeSchemaService())
    with pytest.raises(ValidationError):
        wl.assert_columns("MYCOMPANY_DB", "OITM", ["ItemCode", "EvilCol"])
