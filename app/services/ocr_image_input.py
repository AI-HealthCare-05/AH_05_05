import math
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

import anyio
from fastapi import UploadFile
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.core.exceptions import (
    AppError,
    ImageConversionError,
    ImageTooLargeError,
    InvalidImageError,
    MultiImageNotSupportedError,
    UnsupportedImageFormatError,
)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = MAX_UPLOAD_BYTES
MAX_DIMENSION = 10_000
MAX_DECODED_PIXELS = 40_000_000
MAX_SOURCE_DIMENSION = 16_000
MAX_SOURCE_PIXELS = 64_000_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "HEIF", "WEBP", "BMP", "TIFF", "MPO"}
JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Auxiliary/depth/thumbnail items are not additional user photos. libheif's
# top-level image count still detects real multi-image HEIF containers.
register_heif_opener(thumbnails=False, depth_images=False, aux_images=False)
_decode_limiter = anyio.CapacityLimiter(2)


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    filename: str
    media_type: str
    provider_format: str
    content: bytes


def _detect(content: bytes) -> tuple[str, str] | None:
    if content.startswith(JPEG_SIGNATURE):
        return "image/jpeg", "jpg"
    if content.startswith(PNG_SIGNATURE):
        return "image/png", "png"
    return None


def _check_source(image: Image.Image) -> None:
    # MPO is a JPEG container with secondary camera images. Process only the
    # initial primary frame, never seek/decode auxiliaries, and re-encode below
    # so MPF metadata and additional frames cannot reach storage or OCR.
    if image.format == "GIF" or (image.format != "MPO" and getattr(image, "n_frames", 1) != 1):
        raise MultiImageNotSupportedError()
    if image.format not in SUPPORTED_FORMATS:
        raise UnsupportedImageFormatError()
    width, height = image.size
    if min(width, height) <= 0:
        raise InvalidImageError()
    if max(width, height) > MAX_SOURCE_DIMENSION or width * height > MAX_SOURCE_PIXELS:
        raise ImageTooLargeError()


def _verify_decode(content: bytes) -> None:
    with Image.open(BytesIO(content), formats=["JPEG", "PNG"]) as decoded:
        if max(decoded.size) > MAX_DIMENSION or decoded.width * decoded.height > MAX_DECODED_PIXELS:
            raise ImageTooLargeError()
        if getattr(decoded, "n_frames", 1) != 1:
            raise MultiImageNotSupportedError()
        decoded.load()


def _encode(image: Image.Image, source_format: str) -> bytes:
    # TIFF and HEIF decoders may already apply orientation when loading.
    oriented = ImageOps.exif_transpose(image)
    try:
        scale = min(
            1.0, MAX_DIMENSION / max(oriented.size), math.sqrt(MAX_DECODED_PIXELS / (oriented.width * oriented.height))
        )
        if scale < 1:
            oriented.thumbnail(
                (max(1, int(oriented.width * scale)), max(1, int(oriented.height * scale))),
                Image.Resampling.LANCZOS,
            )
        has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
        mode = "RGBA" if has_alpha else "RGB"
        profile = oriented.info.get("icc_profile")
        if profile:
            converted = ImageCms.profileToProfile(
                oriented, ImageCms.ImageCmsProfile(BytesIO(profile)), ImageCms.createProfile("sRGB"), outputMode=mode
            )
        else:
            converted = oriented.convert(mode)
        if converted is None:
            raise ImageConversionError()
        try:
            stream = BytesIO()
            output_format = "PNG" if has_alpha or source_format == "PNG" else "JPEG"
            # Do not carry EXIF orientation, GPS, XMP or stale source color profiles.
            converted.info.clear()
            converted.save(
                stream, format=output_format, **({"quality": 95, "subsampling": 0} if output_format == "JPEG" else {})
            )
            return stream.getvalue()
        finally:
            converted.close()
    except (OSError, ValueError, TypeError, ImageCms.PyCMSError) as error:
        raise ImageConversionError() from error
    finally:
        oriented.close()


def _normalize(content: bytes, filename: str) -> ValidatedImage:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as candidate:
                _check_source(candidate)
                candidate.verify()
            with Image.open(BytesIO(content)) as decoded:
                _check_source(decoded)
                source_format = decoded.format or ""
                decoded.load()
                needs_conversion = (
                    source_format not in {"JPEG", "PNG"}
                    or decoded.getexif().get(274, 1) != 1
                    or max(decoded.size) > MAX_DIMENSION
                    or decoded.width * decoded.height > MAX_DECODED_PIXELS
                    or decoded.mode not in {"RGB", "RGBA", "L", "LA", "P", "1"}
                )
                if needs_conversion:
                    content = _encode(decoded, source_format)
            if len(content) > MAX_OUTPUT_BYTES:
                raise ImageTooLargeError()
            detected = _detect(content)
            if detected is None:
                raise ImageConversionError()
            if needs_conversion:
                _verify_decode(content)
    except AppError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ImageTooLargeError() from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as error:
        raise InvalidImageError() from error

    # Storage and providers receive metadata describing the output, even when
    # the client supplies a misleading suffix, a path, or no MIME type.
    basename = PurePosixPath(filename.replace("\\", "/")).name
    stem = PurePosixPath(basename).stem or "photo"
    suffix = PurePosixPath(basename).suffix.lower()
    valid_suffixes = {".jpg", ".jpeg"} if detected[1] == "jpg" else {".png"}
    output_name = basename if suffix in valid_suffixes else f"{stem}.{detected[1]}"
    return ValidatedImage(filename=output_name, media_type=detected[0], provider_format=detected[1], content=content)


async def validate_image(upload: UploadFile) -> ValidatedImage:
    if not upload.filename:
        raise InvalidImageError()
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise InvalidImageError()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ImageTooLargeError()
    # Limit native decoding off the ASGI event loop. Cancellation must not release
    # capacity while a decoder is still running and holding its image buffers.
    return await anyio.to_thread.run_sync(_normalize, content, upload.filename, limiter=_decode_limiter)
