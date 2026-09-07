"""JSON authentication endpoints, cookie transport, and CSRF enforcement."""

from collections.abc import Callable
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.services.auth import AuthService
from app.services.auth_types import AuthError, GrantIssued, Identity, Permission

router = APIRouter(prefix="/auth", tags=["authentication"])


class Input(BaseModel):
    """Reject unexpected input properties instead of silently ignoring typos."""

    model_config = ConfigDict(extra="forbid")


class LoginInput(Input):
    """Bound credentials while redacting password representations."""

    account: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=1, max_length=128)


class GrantInput(Input):
    """Accept a one-use token and the user's permanent password."""

    token: SecretStr = Field(min_length=20, max_length=256)
    password: SecretStr = Field(min_length=15, max_length=128)


class PasswordInput(Input):
    """Require proof of the current password before replacement."""

    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=15, max_length=128)


class InviteInput(Input):
    """Allow an Admin to provision an account only into a known role."""

    account: str = Field(min_length=3, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "operator", "reviewer"]
    position: str | None = Field(default=None, max_length=100)


class UserChange(Input):
    """Restrict account administration to explicit role/status changes."""

    role: Literal["admin", "operator", "reviewer"] | None = None
    is_active: bool | None = None


def service(request: Request) -> AuthService:
    """Resolve the app-owned service so tests can inject a disposable database."""
    return request.app.state.auth


def session_token(request: Request) -> str:
    """Read only the configured cookie, bounding untrusted credential length."""
    value = request.cookies.get(service(request).settings.session_cookie, "")
    return value if len(value) <= 256 else ""


def address(request: Request) -> str:
    """Use the server-observed client, never arbitrary forwarded-header input."""
    return request.client.host if request.client else "unknown"


def check_csrf(request: Request) -> None:
    """Require trusted Origin plus a session/pre-auth-cookie-bound proof on writes."""
    auth = service(request)
    allowed = {auth.settings.public_url, *auth.settings.cors_origins}
    origin = request.headers.get("origin", "")
    cookie = session_token(request) or request.cookies.get(auth.settings.csrf_cookie, "")
    if (
        origin not in allowed
        or len(cookie) > 256
        or not auth.tokens.csrf_valid(cookie, request.headers.get("x-csrf-token", ""))
    ):
        raise AuthError("csrf_rejected", 403)
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise AuthError("json_required", 415)


def require_permission(permission: Permission) -> Callable[[Request], Identity]:
    """Build a reusable dependency; mutation services must also check within their transaction."""

    def dependency(request: Request) -> Identity:
        """Authorize from current server-side account state, never client role claims."""
        return service(request).authorize(session_token(request), permission)

    return dependency


def set_cookie(response: Response, auth: AuthService, name: str, value: str, max_age: int) -> None:
    """Apply identical host-only transport controls to session and pre-auth cookies."""
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=auth.settings.secure_cookies,
        samesite="strict",
        path="/",
        max_age=max_age,
    )


def clear_cookies(response: Response, auth: AuthService) -> None:
    """Remove both cookie kinds using their original path and transport attributes."""
    for name in (auth.settings.session_cookie, auth.settings.csrf_cookie):
        response.delete_cookie(
            name, path="/", secure=auth.settings.secure_cookies, httponly=True, samesite="strict"
        )


def grant_response(grant: GrantIssued) -> dict:
    """Show the activation/recovery link once without exposing persisted hashes."""
    return {"user": asdict(grant.user), "purpose": grant.purpose, "url": grant.url}


@router.get("/csrf")
def csrf(request: Request, response: Response) -> dict[str, str]:
    """Supply a CSRF proof without changing an account or extending its session."""
    auth = service(request)
    cookie = session_token(request) or request.cookies.get(auth.settings.csrf_cookie, "")
    if not cookie or len(cookie) > 256:
        cookie = auth.tokens.issue()
        set_cookie(response, auth, auth.settings.csrf_cookie, cookie, 3600)
    return {"csrf_token": auth.tokens.keyed_digest("csrf", cookie)}


@router.post("/login", dependencies=[Depends(check_csrf)])
def login(body: LoginInput, request: Request, response: Response) -> dict:
    """Issue a new session and rotate the cookie-bound CSRF proof after login."""
    auth = service(request)
    issued = auth.login(body.account, body.password.get_secret_value(), address(request))
    set_cookie(
        response,
        auth,
        auth.settings.session_cookie,
        issued.token,
        auth.settings.session_max_seconds,
    )
    response.delete_cookie(
        auth.settings.csrf_cookie,
        path="/",
        secure=auth.settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )
    return {
        "user": asdict(issued.user),
        "csrf_token": auth.tokens.keyed_digest("csrf", issued.token),
    }


@router.get("/me")
def current_user(request: Request) -> dict:
    """Return current account fields without refreshing the idle deadline."""
    return asdict(service(request).current(session_token(request)))


@router.post("/activity", dependencies=[Depends(check_csrf)])
def activity(request: Request) -> dict:
    """Record deliberate foreground activity; the UI must exclude background polling."""
    return asdict(service(request).current(session_token(request), activity=True))


@router.post("/logout", dependencies=[Depends(check_csrf)])
def logout(request: Request, response: Response) -> dict[str, bool]:
    """Invalidate the server session and clear cookies, including expired credentials."""
    auth = service(request)
    auth.logout(session_token(request))
    clear_cookies(response, auth)
    return {"ok": True}


@router.post("/activate", dependencies=[Depends(check_csrf)])
def activate(body: GrantInput, request: Request) -> dict:
    """Consume an activation capability from a JSON body, never a GET URL."""
    return asdict(
        service(request).consume_grant(
            body.token.get_secret_value(),
            "activation",
            body.password.get_secret_value(),
            address(request),
        )
    )


@router.post("/recover", dependencies=[Depends(check_csrf)])
def recover(body: GrantInput, request: Request) -> dict:
    """Consume an Admin-issued recovery link without logging a user in automatically."""
    return asdict(
        service(request).consume_grant(
            body.token.get_secret_value(),
            "recovery",
            body.password.get_secret_value(),
            address(request),
        )
    )


@router.post("/password", dependencies=[Depends(check_csrf)])
def change_password(body: PasswordInput, request: Request, response: Response) -> dict[str, bool]:
    """Replace the password and end all sessions, including this browser session."""
    auth = service(request)
    auth.change_password(
        session_token(request),
        body.current_password.get_secret_value(),
        body.new_password.get_secret_value(),
    )
    clear_cookies(response, auth)
    return {"ok": True}


@router.get("/users")
def list_users(
    request: Request,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    """Page through safe user details for an authenticated Admin."""
    return [
        asdict(user) for user in service(request).list_users(session_token(request), offset, limit)
    ]


@router.post("/users", dependencies=[Depends(check_csrf)], status_code=201)
def invite(body: InviteInput, request: Request) -> dict:
    """Create an invited account and return its Admin-delivered activation link."""
    grant = service(request).invite(
        session_token(request), body.account, body.name, body.role, body.position
    )
    return grant_response(grant)


@router.post("/users/{user_id}/grants/{purpose}", dependencies=[Depends(check_csrf)])
def issue_grant(user_id: int, purpose: Literal["activation", "recovery"], request: Request) -> dict:
    """Replace an activation link or issue recovery only after a current Admin check."""
    return grant_response(service(request).issue_grant(session_token(request), user_id, purpose))


@router.patch("/users/{user_id}", dependencies=[Depends(check_csrf)])
def change_user(user_id: int, body: UserChange, request: Request) -> dict:
    """Apply an Admin role/status change and revoke the target's stale authority."""
    return asdict(
        service(request).change_user(session_token(request), user_id, body.role, body.is_active)
    )
