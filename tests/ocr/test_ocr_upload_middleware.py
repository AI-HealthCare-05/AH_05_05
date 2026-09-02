from starlette.responses import Response
from starlette.types import Message, Receive, Scope, Send

from app.core.ocr_upload_middleware import OcrUploadSizeLimitMiddleware


async def test_streamed_ocr_request_without_content_length_is_bounded() -> None:
    incoming = iter(
        [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"789012", "more_body": False},
        ]
    )
    sent: list[Message] = []

    async def receive() -> Message:
        return next(incoming)  # type: ignore[return-value]

    async def send(message: Message) -> None:
        sent.append(message)

    async def consume_body(scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await Response(status_code=204)(scope, receive, send)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/ocr",
        "headers": [],
    }

    await OcrUploadSizeLimitMiddleware(consume_body, max_request_bytes=10)(scope, receive, send)

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413
