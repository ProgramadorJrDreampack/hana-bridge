"""Tests del mapeo de errores → ErrorResponse."""
import pytest

from core.errors import AuthError, ErrorResponse, HanaError, ValidationError


def test_status_codes():
    assert ValidationError().status_code == 400
    assert AuthError().status_code == 401
    assert HanaError().status_code == 502


def test_to_response_shape():
    resp = ValidationError("dato inválido", details={"campo": "schema"}).to_response("req-1")
    assert isinstance(resp, ErrorResponse)
    assert resp.error_code == "validation_error"
    assert resp.message == "dato inválido"
    assert resp.request_id == "req-1"
    assert resp.details == {"campo": "schema"}


def test_handlers_via_testclient():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from core.error_handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise ValidationError("no permitido", details={"k": "v"})

    client = TestClient(app)
    resp = client.get("/boom")
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "validation_error"
    assert body["message"] == "no permitido"
    assert body["details"] == {"k": "v"}
