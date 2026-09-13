"""FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.production_limits import ProductionLimitsMiddleware
from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domain.numeric import DomainError
from app.services.auth import AuthService
from app.services.auth_types import AuthError


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance.

    Kept as a factory (rather than a bare module-level `app = FastAPI()`)
    so tests can construct fresh, independently-configured app instances
    without import-time side effects leaking between tests.
    """
    settings = get_settings()
    app = FastAPI(title="ProLog API", version="0.1.0")
    app.state.auth = AuthService(SessionLocal, settings)

    @app.exception_handler(DomainError)
    async def production_error(request: Request, error: DomainError) -> JSONResponse:
        """Translate expected production rejections without reflecting submitted values."""
        return JSONResponse({"detail": error.code}, status_code=error.status)

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, error: AuthError) -> JSONResponse:
        """Return only stable domain error codes without exposing credentials."""
        headers = (
            {"Retry-After": str(settings.auth_window_seconds)} if error.status == 429 else None
        )
        return JSONResponse({"detail": error.code}, status_code=error.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, error: RequestValidationError) -> JSONResponse:
        """Omit Pydantic input/context fields, which can contain plaintext passwords."""
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "type": e["type"]} for e in error.errors()]},
            status_code=422,
        )

    @app.exception_handler(ValueError)
    async def invalid_value(request: Request, error: ValueError) -> JSONResponse:
        """Report domain validation without reflecting sensitive submitted values."""
        return JSONResponse({"detail": "invalid_input"}, status_code=400)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        """Fail closed on database errors without returning SQL or bind parameters."""
        return JSONResponse({"detail": "service_unavailable"}, status_code=503)

    @app.middleware("http")
    async def auth_response_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Prevent caching authentication responses and propagation of sensitive referrers."""
        response = await call_next(request)
        if request.url.path.startswith("/auth"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.add_middleware(ProductionLimitsMiddleware)
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
