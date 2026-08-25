import json
import time
import uuid
from pathlib import Path
from typing import cast

import httpx

from app.core.config import Config
from app.core.exceptions import (
    OcrProviderConfigError,
    OcrProviderError,
    OcrProviderTimeoutError,
    OcrProviderTransientError,
)
from app.services.ocr_image_input import ValidatedImage


class ClovaTemplateProvider:
    def __init__(self, settings: Config, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def extract(self, image: ValidatedImage) -> object:
        raw_url = self._settings.CLOVA_TEMPLATE_OCR_INVOKE_URL
        raw_secret = self._settings.CLOVA_TEMPLATE_OCR_SECRET
        template_id = self._settings.CLOVA_TEMPLATE_ID
        url = raw_url.strip() if raw_url is not None else ""
        secret = raw_secret.get_secret_value().strip() if raw_secret is not None else ""
        if not url or not secret or template_id is None:
            raise OcrProviderConfigError()

        message = {
            "version": "V2",
            "requestId": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "lang": "ko",
            "images": [
                {
                    "format": image.provider_format,
                    "name": Path(image.filename).stem,
                    "templateIds": [template_id],
                }
            ],
        }
        timeout = httpx.Timeout(
            connect=self._settings.CLOVA_CONNECT_TIMEOUT_SECONDS,
            read=self._settings.CLOVA_READ_TIMEOUT_SECONDS,
            write=30.0,
            pool=5.0,
        )
        try:
            response = await self._client.post(
                url,
                headers={"X-OCR-SECRET": secret},
                data={"message": json.dumps(message, ensure_ascii=False, separators=(",", ":"))},
                files={"file": (image.filename, image.content, image.media_type)},
                timeout=timeout,
            )
        except httpx.TimeoutException as error:
            raise OcrProviderTimeoutError() from error
        except httpx.RequestError as error:
            raise OcrProviderTransientError() from error

        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            raise OcrProviderTransientError()

        try:
            response.raise_for_status()
            payload = cast(object, response.json())
        except (httpx.HTTPStatusError, ValueError) as error:
            raise OcrProviderError() from error
        if not isinstance(payload, dict):
            raise OcrProviderError()
        return payload
