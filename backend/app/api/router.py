"""Aggregates all versioned sub-routers into a single APIRouter.

Later sections add one `include_router` call each (auth, runs,
measurements, search, export, ...) instead of main.py growing a route
list directly.
"""

from fastapi import APIRouter

from app.api import auth, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
