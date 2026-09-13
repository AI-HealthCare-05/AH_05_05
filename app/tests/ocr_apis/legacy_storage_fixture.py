import asyncio
import hashlib
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.services.ocr_image_input import ValidatedImage


class TemporaryOcrStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, storage_key: str) -> Path:
        if not storage_key or Path(storage_key).name != storage_key:
            raise ValueError("invalid OCR storage key")
        return self.root / storage_key

    async def save(self, image: ValidatedImage) -> str:
        storage_key = f"{uuid4().hex}.{image.provider_format}"
        path = self._path(storage_key)

        def write() -> None:
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f"{path.suffix}.tmp")
            temporary.write_bytes(image.content)
            os.replace(temporary, path)

        await asyncio.to_thread(write)
        return storage_key

    async def save_processed(self, manifest: dict[str, object], content: bytes) -> dict[str, object]:
        if not isinstance(content, bytes) or not content:
            raise ValueError("processed OCR image is missing")
        storage_key = f"{uuid4().hex}.processed.jpg"
        path = self._path(storage_key)

        def write() -> None:
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f"{path.suffix}.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, path)

        await asyncio.to_thread(write)
        return {
            **manifest,
            "processedStorageKey": storage_key,
            "processedContentSha256": hashlib.sha256(content).hexdigest(),
            "processedMediaType": "image/jpeg",
        }

    async def load(self, manifest: dict[str, object]) -> ValidatedImage:
        storage_key = manifest.get("storageKey")
        if not isinstance(storage_key, str):
            raise ValueError("OCR storage key is missing")
        content = await asyncio.to_thread(self._path(storage_key).read_bytes)
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
        storage_key = manifest.get("processedStorageKey")
        if not isinstance(storage_key, str):
            raise ValueError("processed OCR storage key is missing")
        content = await asyncio.to_thread(self._path(storage_key).read_bytes)
        expected_hash = manifest.get("processedContentSha256")
        if not isinstance(expected_hash, str) or hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError("processed OCR image hash mismatch")
        media_type = manifest.get("processedMediaType")
        if media_type != "image/jpeg":
            raise ValueError("processed OCR image media type is invalid")
        return content, media_type

    async def delete(self, manifest: dict[str, object]) -> None:
        for field in ("storageKey", "processedStorageKey"):
            storage_key = manifest.get(field)
            if isinstance(storage_key, str):
                await asyncio.to_thread(self._path(storage_key).unlink, missing_ok=True)

    async def delete_orphans(self, active_storage_keys: set[str], *, older_than: datetime) -> int:
        """Remove stale files that no database row can discover after a partial submit failure."""

        def delete() -> int:
            if not self.root.exists():
                return 0
            deleted = 0
            cutoff = older_than.timestamp()
            for path in self.root.iterdir():
                if not path.is_file() or path.name in active_storage_keys or path.stat().st_mtime > cutoff:
                    continue
                path.unlink(missing_ok=True)
                deleted += 1
            return deleted

        return await asyncio.to_thread(delete)
