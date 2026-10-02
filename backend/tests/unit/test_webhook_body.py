"""The bank webhook reads its body in chunks and stops at the cap (audit finding 9): a chunked request with
no Content-Length must not be buffered whole before the size check."""

import asyncio

import pytest
from starlette.requests import Request

from app.api.routers.records import MAX_WEBHOOK_BYTES, read_capped
from app.core.errors import AppError


def request(
    chunks: list[bytes], content_length: str | None = None
) -> tuple[Request, list[dict[str, object]]]:
    pending: list[dict[str, object]] = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)
    ]

    async def receive() -> dict[str, object]:
        return pending.pop(0)

    headers = [(b"content-length", content_length.encode())] if content_length is not None else []
    return Request({"type": "http", "method": "POST", "headers": headers}, receive), pending


def test_a_small_body_is_returned_whole() -> None:
    req, _ = request([b"ab", b"cd"])
    assert asyncio.run(read_capped(req)) == b"abcd"


def test_an_oversized_chunked_body_is_refused_before_the_rest_is_read() -> None:
    big = b"x" * (MAX_WEBHOOK_BYTES // 2 + 1)
    req, pending = request([big, big, big, big])
    with pytest.raises(AppError):
        asyncio.run(read_capped(req))
    assert len(pending) == 2  # it stopped after the second chunk


def test_a_non_numeric_content_length_is_a_validation_error_not_a_500() -> None:
    req, _ = request([b"ab"], content_length="abc")
    with pytest.raises(AppError):
        asyncio.run(read_capped(req))
