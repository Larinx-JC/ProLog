"""Liveness endpoint used by ops and CI smoke checks."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return a minimal payload proving the API process is up and routing works."""
    return {"status": "ok"}
