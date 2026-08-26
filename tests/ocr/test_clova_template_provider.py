import json
from io import BytesIO

import httpx
import pytest
from fastapi import UploadFile
from PIL import Image

from app.core.config import Config
from app.core.exceptions import (
    OcrProviderConfigError,
    OcrProviderError,
    OcrProviderTimeoutError,
    OcrProviderTransientError,
)
from app.services.clova_template_ocr import ClovaTemplateProvider
from app.services.ocr_image_input import validate_image


def jpeg_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (32, 24), "white").save(stream, format="JPEG")
    return stream.getvalue()


def upload() -> UploadFile:
    return UploadFile(
        filename="guide.jpg",
        file=BytesIO(jpeg_bytes()),
        headers={"content-type": "image/jpeg"},
    )


def settings(**overrides: object) -> Config:
    values: dict[str, object] = {
        "CLOVA_TEMPLATE_OCR_INVOKE_URL": "https://example.test/infer",
        "CLOVA_TEMPLATE_OCR_SECRET": "server-only-secret",
        "CLOVA_TEMPLATE_ID": 43199,
    }
    values.update(overrides)
    return Config(_env_file=None, **values)


async def test_provider_sends_clova_v2_multipart_for_configured_template() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        captured["secret"] = request.headers.get("X-OCR-SECRET")
        captured["body"] = body
        return httpx.Response(
            200,
            json={
                "version": "V2",
                "images": [
                    {
                        "inferResult": "SUCCESS",
                        "matchedTemplate": {"id": 43199, "name": "약"},
                        "fields": [],
                    }
                ],
            },
        )

    image = await validate_image(upload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        payload = await ClovaTemplateProvider(settings(), client).extract(image)

    assert isinstance(payload, dict)
    assert captured["secret"] == "server-only-secret"
    body = bytes(captured["body"])
    assert b'"version":"V2"' in body
    assert b'"format":"jpg"' in body
    assert b'"templateIds":[43199]' in body


async def test_provider_rejects_missing_configuration_before_network_call() -> None:
    image = await validate_image(upload())

    async with httpx.AsyncClient() as client:
        with pytest.raises(OcrProviderConfigError):
            await ClovaTemplateProvider(
                settings(CLOVA_TEMPLATE_OCR_INVOKE_URL=None),
                client,
            ).extract(image)


async def test_provider_maps_timeout_to_project_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    image = await validate_image(upload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OcrProviderTimeoutError):
            await ClovaTemplateProvider(settings(), client).extract(image)


@pytest.mark.parametrize("status_code", [408, 429, 500, 503])
async def test_provider_marks_only_retryable_http_statuses_as_transient(status_code: int) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"message": "temporary"})

    image = await validate_image(upload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OcrProviderTransientError):
            await ClovaTemplateProvider(settings(), client).extract(image)


async def test_provider_keeps_non_retryable_http_errors_permanent() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad request"})

    image = await validate_image(upload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OcrProviderError) as error:
            await ClovaTemplateProvider(settings(), client).extract(image)

    assert not isinstance(error.value, OcrProviderTransientError)


def test_config_repr_does_not_expose_clova_secret() -> None:
    config = settings()

    assert "server-only-secret" not in repr(config)
    assert json.loads(config.model_dump_json())["CLOVA_TEMPLATE_OCR_SECRET"] == "**********"
