from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_OCR_MULTIPART_REQUEST_BYTES = 51 * 1024 * 1024
_OCR_PATH = "/api/v1/ocr/medication-guides"


class _OcrRequestTooLargeError(Exception):
    pass


class OcrUploadSizeLimitMiddleware:
    """OCR multipart 본문이 파싱되기 전에 요청 전체 크기를 제한한다."""

    def __init__(self, app: ASGIApp, max_request_bytes: int = MAX_OCR_MULTIPART_REQUEST_BYTES) -> None:
        self._app = app
        self._max_request_bytes = max_request_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != _OCR_PATH:
            await self._app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self._max_request_bytes:
            await self._reject(scope, receive, send)
            return

        received_bytes = 0

        async def receive_with_limit() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._max_request_bytes:
                    raise _OcrRequestTooLargeError
            return message

        try:
            await self._app(scope, receive_with_limit, send)
        except _OcrRequestTooLargeError:
            await self._reject(scope, receive, send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "code": "OCR_UPLOAD_TOO_LARGE",
                "message": "OCR 요청 크기는 51MB를 초과할 수 없습니다.",
            },
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
        await response(scope, receive, send)
