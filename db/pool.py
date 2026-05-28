"""Pool de conexiones a SAP HANA, thread-safe (Issue #5, Q6=B).

Reemplaza la conexión global no thread-safe del bridge original. Los endpoints
de FastAPI son síncronos (se ejecutan en un threadpool), así que el pool debe
soportar acceso concurrente: usa una cola thread-safe + lock para el contador.

Cada conexión que se entrega pasa un health-check (`isconnected`); si está
muerta, se intenta `reconnect` y, si falla, se descarta y se crea otra.
La factoría de conexión es inyectable para poder testear sin HANA real.
"""
from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from config import Settings
from core.error_log import get_logger
from core.errors import HanaError, PoolTimeoutError

ConnectFn = Callable[[], Any]


class HanaConnectionPool:
    """Pool acotado de conexiones HANA con creación perezosa y reconexión."""

    def __init__(self, settings: Settings, connect_fn: ConnectFn | None = None) -> None:
        self._settings = settings
        self._connect_fn = connect_fn or self._default_connect
        self._pool: queue.LifoQueue[Any] = queue.LifoQueue(maxsize=settings.pool_size)
        self._lock = threading.Lock()
        self._created = 0
        self._closed = False
        self._log = get_logger()

    # ─── Factoría por defecto (hdbcli) ──────────────────────────────────────
    def _default_connect(self) -> Any:
        from hdbcli import dbapi  # import perezoso: el módulo no exige hdbcli para importarse

        return dbapi.connect(
            address=self._settings.hana_host,
            port=self._settings.hana_port,
            user=self._settings.hana_user,
            password=self._settings.hana_password.get_secret_value(),
            encrypt=self._settings.hana_encrypt,
            sslValidateCertificate=self._settings.hana_ssl_validate,
        )

    # ─── Ciclo de vida de conexiones ────────────────────────────────────────
    def _try_create(self) -> Any | None:
        """Crea una conexión si no se alcanzó el máximo. Cuenta protegida por lock."""
        with self._lock:
            if self._created >= self._settings.pool_size:
                return None
            self._created += 1
        try:
            return self._connect_fn()
        except Exception as exc:  # noqa: BLE001 — normalizamos a HanaError
            with self._lock:
                self._created -= 1
            raise HanaError("No se pudo establecer conexión con HANA") from exc

    @staticmethod
    def _is_alive(conn: Any) -> bool:
        try:
            return bool(conn.isconnected())
        except Exception:  # noqa: BLE001
            return False

    def _safe_close(self, conn: Any) -> None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    def _discard(self, conn: Any) -> None:
        self._safe_close(conn)
        with self._lock:
            self._created = max(0, self._created - 1)

    def _ensure_alive(self, conn: Any) -> Any:
        if self._is_alive(conn):
            return conn
        # Intentar reconexión in situ.
        try:
            conn.reconnect()
            if self._is_alive(conn):
                return conn
        except Exception:  # noqa: BLE001
            self._log.warning("Reconexión de conexión HANA falló; recreando")
        self._discard(conn)
        new_conn = self._try_create()
        if new_conn is None:
            raise HanaError("No fue posible recrear la conexión a HANA")
        return new_conn

    def _get(self) -> Any:
        if self._closed:
            raise HanaError("El pool está cerrado")
        try:
            conn = self._pool.get_nowait()
        except queue.Empty:
            created = self._try_create()
            if created is not None:
                return created
            try:
                conn = self._pool.get(timeout=self._settings.pool_acquire_timeout_seconds)
            except queue.Empty as exc:
                raise PoolTimeoutError(
                    "No hay conexiones disponibles; reintenta en unos segundos"
                ) from exc
        return self._ensure_alive(conn)

    def _release(self, conn: Any) -> None:
        if self._closed:
            self._discard(conn)
            return
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            self._discard(conn)

    @contextmanager
    def acquire(self) -> Iterator[Any]:
        """Entrega una conexión sana; la devuelve al pool al salir.

        Si el bloque lanza una excepción, la conexión se descarta (puede haber
        quedado en estado inconsistente) en lugar de reutilizarse.
        """
        conn = self._get()
        try:
            yield conn
        except Exception:
            self._discard(conn)
            raise
        else:
            self._release(conn)

    # ─── Operaciones de gestión ─────────────────────────────────────────────
    def healthy(self) -> bool:
        """True si se puede obtener una conexión viva (usado por /health)."""
        try:
            with self.acquire() as conn:
                return self._is_alive(conn)
        except Exception:  # noqa: BLE001
            return False

    def close_all(self) -> None:
        """Cierra todas las conexiones (shutdown de la app)."""
        self._closed = True
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                break
            self._safe_close(conn)
        with self._lock:
            self._created = 0
