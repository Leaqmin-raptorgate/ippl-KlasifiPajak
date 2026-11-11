"""Reject an oversized receipt upload before the body is spooled to disk.

Starlette parses a multipart body before the handler or authentication runs, so
the 8 MB check in the receipt service cannot protect the disk. This pure ASGI
middleware answers 413 ``PAYLOAD_TOO_LARGE`` from ``Content-Length`` when it is
over the limit, and stops reading the stream once the byte count passes it.
"""

from __future__ import annotations

import json

UPLOAD_PATH_SUFFIX = "/transactions/ocr-upload"
MAX_UPLOAD_BODY_BYTES = 9 * 1024 * 1024
_MESSAGE = "Berkas terlalu besar. Batas unggah 8 MB."


class _TooLarge(Exception):
    pass


class UploadSizeLimitMiddleware:
    def __init__(self, app, limit: int = MAX_UPLOAD_BODY_BYTES) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or not scope.get("path", "").endswith(UPLOAD_PATH_SUFFIX)
        ):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            await self._reject(send)
            return

        seen = 0
        started = False

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise _TooLarge
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not started:
                await self._reject(send)

    @staticmethod
    async def _reject(send) -> None:
        body = json.dumps({"error": {"code": "PAYLOAD_TOO_LARGE", "message": _MESSAGE}}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
