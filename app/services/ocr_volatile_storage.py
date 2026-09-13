"""Bounded Redis storage for short-lived OCR images.

The adapter deliberately stores only bytes in Redis.  Job lifecycle and database
state remain the responsibility of the OCR job service.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

import redis.asyncio as redis

from app.services.ocr_image_input import ValidatedImage

MAX_IMAGE_BYTES = 50 * 1024 * 1024
STORAGE_BACKEND = "volatile-redis-v1"
_KEY_PATTERN = re.compile(r"^ocr-image:[0-9a-f]{32}(?::processed)?$")


class VolatileOcrStorage:
    """Store original and processed OCR previews only in a memory-only Redis."""

    def __init__(self, redis_url: str, ttl_seconds: int, client: Any | None = None) -> None:
        if not isinstance(redis_url, str) or not redis_url.strip():
            raise ValueError("OCR volatile Redis URL is required")
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise ValueError("OCR volatile storage TTL must be positive")

        self.ttl_seconds = ttl_seconds
        self._client = client or redis.Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._owns_client = client is None

    @staticmethod
    def _config_value(config: dict[Any, Any], name: str) -> str | None:
        value = config.get(name)
        if value is None:
            value = config.get(name.encode())
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip()
        return value.strip() if isinstance(value, str) else None

    @staticmethod
    def _is_path_like(storage_key: str) -> bool:
        return "/" in storage_key or "\\" in storage_key or storage_key in {".", ".."}

    @classmethod
    def _require_key(cls, storage_key: object, *, field: str) -> str:
        if not isinstance(storage_key, str) or not _KEY_PATTERN.fullmatch(storage_key):
            raise ValueError(f"invalid OCR storage key in {field}")
        return storage_key

    @classmethod
    def _delete_key(cls, storage_key: object, *, field: str) -> str | None:
        if not isinstance(storage_key, str):
            return None
        if cls._is_path_like(storage_key):
            raise ValueError(f"invalid OCR storage key in {field}")
        return storage_key if _KEY_PATTERN.fullmatch(storage_key) else None

    @staticmethod
    def _require_content(content: object, *, label: str) -> bytes:
        if not isinstance(content, bytes) or not content:
            raise ValueError(f"{label} OCR image is missing")
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError(f"{label} OCR image is too large")
        return content

    @staticmethod
    def _require_backend(manifest: dict[str, object]) -> None:
        if manifest.get("storageBackend") != STORAGE_BACKEND:
            raise ValueError("OCR storage backend is invalid")

    async def _ensure_memory_only(self) -> None:
        values: dict[str, str] = {}
        try:
            for parameter in ("save", "appendonly", "maxmemory", "maxmemory-policy"):
                response = await self._client.config_get(parameter)
                if not isinstance(response, dict):
                    raise TypeError("invalid Redis CONFIG response")
                value = self._config_value(response, parameter)
                if value is None:
                    raise ValueError("missing Redis CONFIG value")
                values[parameter] = value
        except Exception as error:
            raise OSError("OCR volatile storage is unavailable") from error

        try:
            maxmemory = int(values["maxmemory"])
        except ValueError as error:
            raise OSError("OCR volatile storage configuration is unsafe") from error
        if (
            values["save"]
            or values["appendonly"].lower() != "no"
            or maxmemory <= 0
            or values["maxmemory-policy"].lower() != "noeviction"
        ):
            raise OSError("OCR volatile storage configuration is unsafe")

    async def _save_bytes(self, content: bytes, *, suffix: str = "") -> str:
        await self._ensure_memory_only()
        for _ in range(3):
            storage_key = f"ocr-image:{uuid4().hex}{suffix}"
            try:
                saved = await self._client.set(storage_key, content, ex=self.ttl_seconds, nx=True)
            except Exception as error:
                raise OSError("OCR volatile storage is unavailable or at capacity") from error
            if saved:
                return storage_key
        raise OSError("OCR volatile storage is unavailable or at capacity")

    async def _get_bytes(self, storage_key: str) -> bytes:
        try:
            content = await self._client.get(storage_key)
        except Exception as error:
            raise OSError("OCR volatile storage is unavailable") from error
        if content is None:
            raise OSError("OCR temporary image is no longer available")
        if not isinstance(content, bytes) or not content or len(content) > MAX_IMAGE_BYTES:
            raise ValueError("OCR temporary image data is invalid")
        return content

    async def save(self, image: ValidatedImage) -> str:
        return await self._save_bytes(self._require_content(image.content, label="source"))

    async def save_processed(self, manifest: dict[str, object], content: bytes) -> dict[str, object]:
        content = self._require_content(content, label="processed")
        storage_key = await self._save_bytes(content, suffix=":processed")
        return {
            **manifest,
            "processedStorageKey": storage_key,
            "processedContentSha256": hashlib.sha256(content).hexdigest(),
            "processedMediaType": "image/jpeg",
            "storageBackend": STORAGE_BACKEND,
        }

    async def load(self, manifest: dict[str, object]) -> ValidatedImage:
        self._require_backend(manifest)
        storage_key = self._require_key(manifest.get("storageKey"), field="storageKey")
        content = await self._get_bytes(storage_key)
        expected_hash = manifest.get("contentSha256")
        if not isinstance(expected_hash, str) or hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError("OCR temporary image hash mismatch")
        filename = manifest.get("filename")
        media_type = manifest.get("mediaType")
        provider_format = manifest.get("providerFormat")
        if not all(isinstance(value, str) and value for value in (filename, media_type, provider_format)):
            raise ValueError("OCR image metadata is incomplete")
        return ValidatedImage(
            filename=str(filename),
            media_type=str(media_type),
            provider_format=str(provider_format),
            content=content,
        )

    async def load_processed(self, manifest: dict[str, object]) -> tuple[bytes, str]:
        self._require_backend(manifest)
        storage_key = self._require_key(manifest.get("processedStorageKey"), field="processedStorageKey")
        content = await self._get_bytes(storage_key)
        expected_hash = manifest.get("processedContentSha256")
        if not isinstance(expected_hash, str) or hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError("processed OCR image hash mismatch")
        media_type = manifest.get("processedMediaType")
        if media_type != "image/jpeg":
            raise ValueError("processed OCR image media type is invalid")
        return content, str(media_type)

    async def delete(self, manifest: dict[str, object]) -> None:
        keys = [
            key
            for field in ("storageKey", "processedStorageKey")
            if (key := self._delete_key(manifest.get(field), field=field)) is not None
        ]
        if not keys:
            return
        try:
            await self._client.delete(*keys)
        except Exception as error:
            raise OSError("OCR volatile storage is unavailable") from error

    async def touch(self, manifest: dict[str, object]) -> bool:
        keys = [
            self._require_key(manifest.get(field), field=field)
            for field in ("storageKey", "processedStorageKey")
            if manifest.get(field) is not None
        ]
        if not keys:
            return False
        await self._ensure_memory_only()
        try:
            refreshed = await asyncio.gather(*(self._client.expire(key, self.ttl_seconds) for key in keys))
        except Exception as error:
            raise OSError("OCR volatile storage is unavailable") from error
        return all(bool(value) for value in refreshed)

    async def delete_orphans(self, active_storage_keys: set[str], *, older_than: datetime) -> int:
        """TTL bounds all volatile data, so orphan scanning is neither needed nor safe."""
        return 0

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
