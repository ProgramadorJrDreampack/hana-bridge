"""Healthcheck (sin auth, igual que el bridge original)."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    """Reporta el estado del bridge y de la conexión a HANA."""
    pool = request.app.state.pool
    return {"ok": True, "hana": pool.healthy()}
