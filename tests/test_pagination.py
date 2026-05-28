"""Tests de la metadata de paginación."""
from models.pagination import build_page


def test_meta_pagina_intermedia():
    r = build_page([{"a": 1}], total=45, page=2, page_size=20)
    assert r.pagination.total_pages == 3
    assert r.pagination.has_next is True
    assert r.pagination.has_prev is True


def test_meta_primera_pagina():
    r = build_page([], total=10, page=1, page_size=20)
    assert r.pagination.total_pages == 1
    assert r.pagination.has_next is False
    assert r.pagination.has_prev is False


def test_meta_ultima_pagina():
    r = build_page([{"a": 1}], total=40, page=2, page_size=20)
    assert r.pagination.total_pages == 2
    assert r.pagination.has_next is False
    assert r.pagination.has_prev is True


def test_meta_vacia():
    r = build_page([], total=0, page=1, page_size=20)
    assert r.pagination.total_pages == 0
    assert r.pagination.has_next is False
