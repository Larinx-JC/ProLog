"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance.

    Kept as a factory (rather than a bare module-level `app = FastAPI()`)
    so tests can construct fresh, independently-configured app instances
    without import-time side effects leaking between tests.
    """
    settings = get_settings()
    app = FastAPI(title="ProLog API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    return app


app = create_app()
