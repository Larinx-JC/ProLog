"""Declared and streamed request-body bounds, including early rejection and disconnects."""

import asyncio

import pytest
from starlette.responses import Response

from app.api.production_limits import MAX_BODY_BYTES, ProductionLimitsMiddleware


def exchange(
    chunks: list[dict],
    headers: list[tuple[bytes, bytes]],
    path="/production/runs",
    protocol="http",
    method="POST",
) -> tuple[list[dict], list[bytes]]:
    """Drive the ASGI middleware directly to control framing independently of TestClient."""
    sent, received = [], []

    async def receive():
        """Deliver controlled body messages, then a client disconnect."""
        return chunks.pop(0) if chunks else {"type": "http.disconnect"}

    async def send(message):
        """Capture status, headers and body for observable assertions."""
        sent.append(message)

    async def downstream(scope, request, respond):
        """Observe whether rejected input reaches the application."""
        message = await request()
        received.append(message.get("body", b""))
        assert (await request())["type"] == "http.disconnect"
        await Response("ok")(scope, request, respond)

    scope = dict(type=protocol, path=path, method=method, headers=headers)
    asyncio.run(ProductionLimitsMiddleware(downstream)(scope, receive, send))
    return sent, received


@pytest.mark.parametrize(
    "length,status", [(b"65537", 413), (b"-1", 400), (b"abc", 400), (b"999999999999999", 400)]
)
def test_declared_body_rejected_early(length: bytes, status: int) -> None:
    """Bad declared lengths fail before the application consumes any body."""
    sent, received = exchange([], [(b"content-length", length)])
    assert sent[0]["status"] == status and received == []
    assert (b"cache-control", b"no-store") in sent[0]["headers"]


def test_chunked_limit_and_exact_boundary() -> None:
    """The actual streamed size is bounded even when length is absent or dishonest."""
    chunks = [
        {"type": "http.request", "body": b"x" * MAX_BODY_BYTES, "more_body": True},
        {"type": "http.request", "body": b"x", "more_body": False},
    ]
    sent, received = exchange(chunks, [(b"content-length", b"1")])
    assert sent[0]["status"] == 413 and received == []
    exact = b"x" * MAX_BODY_BYTES
    sent, received = exchange([{"type": "http.request", "body": exact}], [])
    assert sent[0]["status"] == 200 and received == [exact]


def test_disconnect_and_unrelated_routes() -> None:
    """Disconnects do not invoke handlers; unrelated routes/protocols pass through."""
    assert exchange([], []) == ([], [])
    for path, protocol, method in (
        ("/auth/login", "http", "POST"),
        ("/production", "websocket", "GET"),
        ("/production/runs", "http", "GET"),
    ):
        sent, received = exchange(
            [{"type": "http.request", "body": b"passed"}], [], path, protocol, method
        )
        assert received == [b"passed"] and sent[0]["status"] == 200
