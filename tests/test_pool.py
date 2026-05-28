"""Tests del pool de conexiones (Issue #5) con una conexión fake (sin HANA)."""
import pytest

from config import Settings
from core.errors import PoolTimeoutError
from db.pool import HanaConnectionPool


class FakeConn:
    def __init__(self):
        self.alive = True
        self.closed = False
        self.reconnects = 0

    def isconnected(self):
        return self.alive and not self.closed

    def reconnect(self):
        self.reconnects += 1
        self.alive = True

    def close(self):
        self.closed = True


def _settings(pool_size=2):
    return Settings(
        api_token="t",
        hana_host="h",
        hana_user="u",
        hana_password="p",
        pool_size=pool_size,
        pool_acquire_timeout_seconds=0.2,
    )


def test_reutiliza_conexion():
    created = []

    def factory():
        c = FakeConn()
        created.append(c)
        return c

    pool = HanaConnectionPool(_settings(2), connect_fn=factory)
    with pool.acquire() as c1:
        assert c1.isconnected()
    with pool.acquire():
        pass
    assert len(created) == 1  # la segunda vez reutilizó la del pool


def test_reconecta_conexion_muerta():
    pool = HanaConnectionPool(_settings(1), connect_fn=FakeConn)
    with pool.acquire() as c1:
        c1.alive = False  # se "muere" estando en uso; vuelve al pool muerta
    with pool.acquire() as c2:
        assert c2.isconnected()
        assert c2.reconnects == 1


def test_timeout_si_pool_agotado():
    pool = HanaConnectionPool(_settings(1), connect_fn=FakeConn)
    holder = pool.acquire()
    holder.__enter__()  # retiene la única conexión
    try:
        with pytest.raises(PoolTimeoutError):
            with pool.acquire():
                pass
    finally:
        holder.__exit__(None, None, None)


def test_descarta_conexion_en_error():
    created = []

    def factory():
        c = FakeConn()
        created.append(c)
        return c

    pool = HanaConnectionPool(_settings(2), connect_fn=factory)
    with pytest.raises(RuntimeError):
        with pool.acquire():
            raise RuntimeError("fallo en el bloque")
    # la conexión con error se descarta; una nueva acquire crea otra
    with pool.acquire() as c:
        assert c.isconnected()
    assert len(created) == 2


def test_close_all():
    created = []

    def factory():
        c = FakeConn()
        created.append(c)
        return c

    pool = HanaConnectionPool(_settings(2), connect_fn=factory)
    with pool.acquire():
        pass
    pool.close_all()
    assert all(c.closed for c in created)
