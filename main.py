"""HANA Bridge API — punto de entrada.

App factory + lifespan: al arrancar se construye el pool de conexiones y los
servicios (una sola vez) y se guardan en `app.state`; al apagar se cierra el
pool. El pool NO conecta de inmediato (creación perezosa), así que la app
levanta aunque HANA esté caído — `/health` reportará `hana: false`.

Arranque: `uvicorn main:app --host 0.0.0.0 --port 8080`
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import get_settings
from core.error_handlers import register_exception_handlers
from core.error_log import configure_logging, get_logger
from db.pool import HanaConnectionPool
from db.repository import Repository
from db.whitelist import Whitelist
from routes import health, production, sales, schema
from routes import table as table_routes
from services.generic_service import GenericService
from services.production_service import ProductionService
from services.sales_service import SalesService
from services.schema_service import SchemaService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, settings.error_log_file)
    log = get_logger()

    pool = HanaConnectionPool(settings)
    repository = Repository(pool)
    schema_service = SchemaService(repository, settings)
    whitelist = Whitelist(settings, schema_service)

    app.state.settings = settings
    app.state.pool = pool
    app.state.repository = repository
    app.state.schema_service = schema_service
    app.state.whitelist = whitelist
    app.state.sales_service = SalesService(repository, whitelist)
    app.state.production_service = ProductionService(repository, whitelist)
    app.state.generic_service = GenericService(repository, whitelist)

    log.info("HANA Bridge iniciado (pool_size=%s, env=%s)", settings.pool_size, settings.app_env)
    try:
        yield
    finally:
        pool.close_all()
        log.info("HANA Bridge detenido; pool cerrado")


def create_app() -> FastAPI:
    app = FastAPI(title="HANA Bridge API", version="2.0.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(sales.router)
    app.include_router(production.router)
    app.include_router(schema.router)
    app.include_router(table_routes.router)
    return app


app = create_app()
