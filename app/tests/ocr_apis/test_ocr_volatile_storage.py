from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest

from app.services.ocr_image_input import ValidatedImage
from app.services.ocr_volatile_storage import VolatileOcrStorage


class FakeRedis:
    def __init__(self, *, config: dict[str, str] | None = None) -> None:
        self.config = config or {
            "save": "",
            "appendonly": "no",
            "maxmemory": "104857600",
            "maxmemory-policy": "noeviction",
        }
        self.values: dict[str, bytes] = {}
        self.expirations: dict[str, int] = {}
        self.closed = False

    async def config_get(self, parameter: str) -> dict[bytes, bytes]:
        return {parameter.encode(): self.config[parameter].encode()}

    async def set(self, key: str, value: bytes, *, ex: int, nx: bool) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expirations[key] = ex
        return True

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.values:
                deleted += 1
            self.values.pop(key, None)
            self.expirations.pop(key, None)
        return deleted

    async def expire(self, key: str, seconds: int) -> bool:
        if key not in self.values:
            return False
        self.expirations[key] = seconds
        return True

    async def aclose(self) -> None:
        self.closed = True


def image(content: bytes = b"source-image") -> ValidatedImage:
    return ValidatedImage("guide.png", "image/png", "png", content)


@pytest.mark.asyncio
async def test_save_and_load_keep_original_in_redis_with_ttl() -> None:
    client = FakeRedis()
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=120, client=client)

    key = await storage.save(image())
    loaded = await storage.load(
        {
            "storageKey": key,
            "contentSha256": hashlib.sha256(b"source-image").hexdigest(),
            "filename": "guide.png",
            "mediaType": "image/png",
            "providerFormat": "png",
            "storageBackend": "volatile-redis-v1",
        }
    )

    assert key.startswith("ocr-image:")
    assert "/" not in key
    assert loaded == image()
    assert client.values[key] == b"source-image"
    assert client.expirations[key] == 120


@pytest.mark.asyncio
async def test_processed_preview_has_hash_media_and_volatile_backend_marker() -> None:
    client = FakeRedis()
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=60, client=client)

    manifest = await storage.save_processed({"storageKey": "ocr-image:" + "a" * 32}, b"processed-jpeg")
    content, media_type = await storage.load_processed(manifest)

    assert manifest["storageBackend"] == "volatile-redis-v1"
    assert str(manifest["processedStorageKey"]).startswith("ocr-image:")
    assert manifest["processedContentSha256"] == hashlib.sha256(b"processed-jpeg").hexdigest()
    assert (content, media_type) == (b"processed-jpeg", "image/jpeg")


@pytest.mark.asyncio
async def test_writes_fail_closed_when_redis_is_not_memory_only() -> None:
    client = FakeRedis(config={"save": "900 1", "appendonly": "no", "maxmemory": "1", "maxmemory-policy": "noeviction"})
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=60, client=client)

    with pytest.raises(OSError, match="volatile storage"):
        await storage.save(image())

    assert client.values == {}


@pytest.mark.asyncio
async def test_load_rejects_missing_or_tampered_images() -> None:
    client = FakeRedis()
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=60, client=client)
    manifest = {
        "storageKey": "ocr-image:" + "b" * 32,
        "contentSha256": hashlib.sha256(b"expected").hexdigest(),
        "filename": "guide.png",
        "mediaType": "image/png",
        "providerFormat": "png",
        "storageBackend": "volatile-redis-v1",
    }

    with pytest.raises(OSError, match="no longer available"):
        await storage.load(manifest)

    client.values[str(manifest["storageKey"])] = b"tampered"
    with pytest.raises(ValueError, match="hash mismatch"):
        await storage.load(manifest)

    client.values[str(manifest["storageKey"])] = b"expected"
    manifest["storageBackend"] = "disk"
    with pytest.raises(ValueError, match="backend"):
        await storage.load(manifest)


@pytest.mark.asyncio
async def test_path_like_handle_is_rejected_and_delete_only_removes_volatile_keys() -> None:
    client = FakeRedis()
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=60, client=client)
    client.values["legacy-file.png"] = b"must-not-touch"

    with pytest.raises(ValueError, match="invalid OCR storage key"):
        await storage.delete({"storageKey": "../../legacy-file.png"})

    await storage.delete({"storageKey": "legacy-file.png"})
    assert client.values["legacy-file.png"] == b"must-not-touch"


@pytest.mark.asyncio
async def test_delete_removes_sensitive_bytes_even_when_redis_becomes_unsafe() -> None:
    client = FakeRedis()
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=60, client=client)
    key = await storage.save(image())
    client.config["save"] = "900 1"

    await storage.delete({"storageKey": key})

    assert key not in client.values


@pytest.mark.asyncio
async def test_touch_refreshes_existing_keys_without_recreating_expired_keys() -> None:
    client = FakeRedis()
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=77, client=client)
    original_key = await storage.save(image())
    manifest = await storage.save_processed({"storageKey": original_key}, b"processed")

    assert await storage.touch(manifest) is True
    assert client.expirations[original_key] == 77
    processed_key = str(manifest["processedStorageKey"])
    client.values.pop(original_key)

    assert await storage.touch(manifest) is False
    assert original_key not in client.values
    assert processed_key in client.values


@pytest.mark.asyncio
async def test_size_ttl_and_orphan_contract_are_bounded() -> None:
    client = FakeRedis()
    with pytest.raises(ValueError, match="TTL"):
        VolatileOcrStorage("redis://volatile", ttl_seconds=0, client=client)

    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=60, client=client)
    with pytest.raises(ValueError, match="too large"):
        await storage.save(image(b"x" * (50 * 1024 * 1024 + 1)))

    assert await storage.delete_orphans(set(), older_than=datetime.now() - timedelta(hours=1)) == 0
