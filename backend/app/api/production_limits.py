"""Bound production JSON bodies before parsing and prevent caching of production responses."""

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 64 * 1024


class ProductionLimitsMiddleware:
    """Enforce limits on declared and streamed lengths without trusting Content-Length alone."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap only production HTTP routes, keeping unrelated protocols/routes unchanged."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Buffer at most the allowed request size, then replay it to normal FastAPI parsing."""
        if scope["type"] != "http" or not scope["path"].startswith("/production"):
            await self.app(scope, receive, send)
            return

        async def no_cache(message: Message) -> None:
            """Set the same cache/referrer policy for success and error responses."""
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Pragma"] = "no-cache"
                headers["Referrer-Policy"] = "no-referrer"
            await send(message)

        async def reject(code: str, status: int) -> None:
            """Reject transport errors without echoing the body or credential-bearing headers."""
            await JSONResponse({"detail": code}, status_code=status)(scope, receive, no_cache)

        if scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, no_cache)
            return
        length = Headers(scope=scope).get("content-length")
        if length is not None:
            if not length.isascii() or not length.isdecimal() or len(length) > 10:
                await reject("invalid_content_length", 400)
                return
            if int(length) > MAX_BODY_BYTES:
                await reject("request_too_large", 413)
                return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                await reject("request_too_large", 413)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay() -> Message:
            """Deliver the validated buffered body once, then preserve disconnect semantics."""
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, no_cache)
