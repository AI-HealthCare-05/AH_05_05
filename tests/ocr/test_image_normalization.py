from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image
from pillow_heif import register_heif_opener

from app.core.exceptions import InvalidImageError
from app.services import ocr_image_input as inputs

register_heif_opener()


def encoded(fmt="PNG", *, mode="RGB", size=(64, 48), **options):
    stream = BytesIO()
    image = Image.new(mode, size, "white")
    if fmt == "HEIF" and "exif" in options:
        # The plugin derives HEIF irot from image.info, not the save kwarg.
        # EXIF alone is descriptive and must not cause a second HEIF rotation.
        image.info["exif"] = options.pop("exif").tobytes()
    image.save(stream, format=fmt, **options)
    return stream.getvalue()


async def normalize(content, name="photo.bin", mime="application/octet-stream"):
    return await inputs.validate_image(UploadFile(filename=name, file=BytesIO(content), headers={"content-type": mime}))


@pytest.mark.parametrize("fmt,ext", [("HEIF", "heic"), ("WEBP", "webp"), ("BMP", "bmp"), ("TIFF", "tiff")])
async def test_single_image_converts_to_real_jpeg(fmt, ext):
    result = await normalize(encoded(fmt), f"photo.{ext}", f"image/{ext}")
    assert (result.filename, result.media_type, result.provider_format) == ("photo.jpg", "image/jpeg", "jpg")
    with Image.open(BytesIO(result.content)) as decoded:
        decoded.load()
        assert (decoded.format, decoded.mode, decoded.size) == ("JPEG", "RGB", (64, 48))


@pytest.mark.parametrize("fmt,mime,ext", [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png")])
async def test_supported_image_preserves_bytes_but_corrects_metadata(fmt, mime, ext):
    source = encoded(fmt)
    result = await normalize(source, "photo.HEIC", "")
    assert result.content == source
    assert (result.filename, result.media_type, result.provider_format) == (f"photo.{ext}", mime, ext)


async def test_transparent_webp_becomes_lossless_png():
    stream = BytesIO()
    Image.new("RGBA", (32, 24), (12, 34, 56, 100)).save(stream, format="WEBP", lossless=True)
    result = await normalize(stream.getvalue())
    assert result.provider_format == "png"
    with Image.open(BytesIO(result.content)) as decoded:
        assert decoded.getpixel((0, 0)) == (12, 34, 56, 100)


@pytest.mark.parametrize("broken_secondary", [False, True])
async def test_mpo_uses_primary_photo_and_removes_other_images(broken_secondary):
    source = encoded("MPO", save_all=True, append_images=[Image.new("RGB", (64, 48), "black")])
    with Image.open(BytesIO(source)) as image:
        assert image.format == "MPO"
        assert image.n_frames == 2
    if broken_secondary:
        # The primary JPEG is valid even if an MPF entry points at bad auxiliary data.
        secondary = source.index(b"\xff\xd8\xff", 3)
        source = source[:secondary] + b"broken auxiliary image"
    result = await normalize(source, "iphone.heic", "image/heic")
    assert (result.filename, result.media_type, result.provider_format) == ("iphone.jpg", "image/jpeg", "jpg")
    with Image.open(BytesIO(result.content)) as image:
        image.load()
        assert image.format == "JPEG"
        assert getattr(image, "n_frames", 1) == 1
        assert image.size == (64, 48)
        assert min(image.getpixel((32, 24))) > 240
        assert "mp" not in image.info


async def test_mpo_primary_orientation_is_applied_once():
    exif = Image.Exif()
    exif[274] = 6
    source = encoded("MPO", exif=exif, save_all=True, append_images=[Image.new("RGB", (64, 48), "black")])
    result = await normalize(source, "camera.mpo")
    with Image.open(BytesIO(result.content)) as image:
        assert image.size == (48, 64)
        assert image.getexif().get(274, 1) == 1


@pytest.mark.parametrize("fmt", ["JPEG", "TIFF", "HEIF"])
async def test_orientation_is_applied_once(fmt):
    exif = Image.Exif()
    exif[274] = 6
    result = await normalize(encoded(fmt, exif=exif))
    with Image.open(BytesIO(result.content)) as decoded:
        assert decoded.size == (48, 64)
        assert decoded.getexif().get(274, 1) == 1


@pytest.mark.parametrize("fmt", ["GIF", "WEBP", "TIFF", "HEIF", "PNG"])
async def test_multiframe_is_rejected_even_when_named_jpeg(fmt):
    content = encoded(fmt, save_all=True, append_images=[Image.new("RGB", (64, 48), "black")])
    with pytest.raises(InvalidImageError) as error:
        await normalize(content, "photo.jpg", "image/jpeg")
    assert error.value.code == "MULTI_IMAGE_NOT_SUPPORTED"


async def test_static_gif_is_also_rejected():
    with pytest.raises(InvalidImageError) as error:
        await normalize(encoded("GIF"))
    assert error.value.code == "MULTI_IMAGE_NOT_SUPPORTED"


@pytest.mark.parametrize("content", [b"", b"not an image", b"\xff\xd8\xffbroken"])
async def test_corrupt_input_is_rejected(content):
    with pytest.raises(InvalidImageError):
        await normalize(content, "photo.jpg", "image/jpeg")


async def test_unsupported_real_image_is_rejected():
    with pytest.raises(InvalidImageError) as error:
        await normalize(encoded("PPM"))
    assert error.value.code == "UNSUPPORTED_IMAGE_FORMAT"


async def test_oversized_output_is_rejected(monkeypatch):
    source = encoded("BMP")
    monkeypatch.setattr(inputs, "MAX_UPLOAD_BYTES", len(source) + 1)
    # Source passes; force the smaller output byte budget independently.
    monkeypatch.setattr(inputs, "MAX_OUTPUT_BYTES", 10, raising=False)
    with pytest.raises(InvalidImageError) as error:
        await normalize(source)
    assert error.value.code == "IMAGE_TOO_LARGE"


async def test_pixel_limits_resize_and_reject_before_decoding(monkeypatch):
    monkeypatch.setattr(inputs, "MAX_DECODED_PIXELS", 2000)
    monkeypatch.setattr(inputs, "MAX_SOURCE_PIXELS", 4000, raising=False)
    result = await normalize(encoded("JPEG", size=(64, 48)))
    with Image.open(BytesIO(result.content)) as decoded:
        assert decoded.width * decoded.height <= 2000
    with pytest.raises(InvalidImageError) as error:
        await normalize(encoded("JPEG", size=(80, 60)))
    assert error.value.code == "IMAGE_TOO_LARGE"


async def test_normalized_image_roundtrips_storage_and_provider():
    import hashlib

    import httpx2

    from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
    from app.services.ocr_volatile_storage import STORAGE_BACKEND, VolatileOcrStorage
    from app.tests.ocr_apis.test_ocr_volatile_storage import FakeRedis

    image = await normalize(encoded("HEIF"), "iphone.heic", "image/heic")
    redis = FakeRedis()
    storage = VolatileOcrStorage("redis://volatile", ttl_seconds=120, client=redis)
    key = await storage.save(image)
    manifest = {
        "storageBackend": STORAGE_BACKEND,
        "storageKey": key,
        "contentSha256": hashlib.sha256(image.content).hexdigest(),
        "filename": image.filename,
        "mediaType": image.media_type,
        "providerFormat": image.provider_format,
    }
    loaded = await storage.load(manifest)
    assert loaded == image
    assert redis.expirations[key] == 120
    from app.services.medication_ocr_v3.pipeline.preprocess import _decode_image

    decoded, fmt, _ = _decode_image(loaded.content, loaded.media_type)
    assert fmt == "JPEG"
    decoded.close()

    def handle(request):
        body = request.read()
        assert b'filename="processed-image.jpg"' in body
        assert b"Content-Type: image/jpeg" in body
        assert image.content in body
        assert b'"format": "jpg"' in body or b'"format":"jpg"' in body
        return httpx2.Response(
            200,
            json={
                "version": "V2",
                "requestId": "test",
                "timestamp": 1,
                "images": [{"inferResult": "SUCCESS", "fields": []}],
            },
        )

    async with ClovaGeneralOcrProvider(
        endpoint="https://example.test/infer", secret="test-only", transport=httpx2.MockTransport(handle)
    ) as provider:
        await provider.recognize(loaded.content)
    await storage.delete(manifest)
    assert key not in redis.values


async def test_48mp_jpeg_is_resized_for_existing_ocr_limit():
    result = await normalize(encoded("JPEG", size=(8000, 6000)), "48mp.jpg", "image/jpeg")
    with Image.open(BytesIO(result.content)) as image:
        assert image.width * image.height <= 40_000_000
        assert abs(image.width / image.height - 4 / 3) < 0.001


async def test_source_bytes_limit_and_missing_filename(monkeypatch):
    source = encoded("PNG")
    monkeypatch.setattr(inputs, "MAX_UPLOAD_BYTES", len(source) - 1)
    with pytest.raises(InvalidImageError) as error:
        await normalize(source)
    assert error.value.code == "IMAGE_TOO_LARGE"
    with pytest.raises(InvalidImageError):
        await normalize(source, "")


async def test_convert_error_has_actionable_message():
    with pytest.raises(InvalidImageError) as error:
        await normalize(encoded("TIFF", icc_profile=b"invalid profile"))
    assert error.value.code == "IMAGE_CONVERSION_FAILED"


@pytest.mark.parametrize(
    "fmt,status,code", [("HEIF", 202, None), ("MPO", 202, None), ("GIF", 422, "MULTI_IMAGE_NOT_SUPPORTED")]
)
async def test_api_memory_upload_normalizes_or_rejects(fmt, status, code):
    from httpx import ASGITransport, AsyncClient

    from app.dependencies.medication_guide_ocr import get_medication_guide_ocr_job_service
    from app.dependencies.security import get_request_user
    from app.dtos.medication_guide_ocr import OcrJobAcceptedResponse
    from app.main import app
    from app.models.enums import OcrJobStatus

    accepted = []

    class NormalizingService:
        async def submit(self, user, idempotency_key, upload):
            assert isinstance(upload.file, BytesIO)
            accepted.append(await inputs.validate_image(upload))
            return OcrJobAcceptedResponse(ocr_job_id="42", status=OcrJobStatus.QUEUED, status_url="/api/v1/ocr/jobs/42")

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_request_user] = lambda: object()
    app.dependency_overrides[get_medication_guide_ocr_job_service] = NormalizingService
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr",
                files={
                    "file": (
                        "image.heic",
                        encoded(
                            fmt,
                            **(
                                {"save_all": True, "append_images": [Image.new("RGB", (64, 48), "black")]}
                                if fmt == "MPO"
                                else {}
                            ),
                        ),
                        "application/octet-stream",
                    )
                },
                headers={"Idempotency-Key": "normalization-test-key"},
            )
        assert response.status_code == status
        if code:
            assert response.json()["code"] == code
            assert not accepted
        else:
            assert accepted[0].provider_format == "jpg"
            assert accepted[0].media_type == "image/jpeg"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
