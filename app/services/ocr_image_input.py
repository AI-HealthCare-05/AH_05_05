import warnings
from dataclasses import dataclass
from io import BytesIO

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.exceptions import AppError, InvalidImageError

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_DIMENSION = 10_000
MAX_DECODED_PIXELS = 40_000_000
JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def _verify_decode(content: bytes) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as candidate:
                candidate.verify()
            with Image.open(BytesIO(content)) as decoded:
                width, height = decoded.size
                if (
                    width <= 0
                    or height <= 0
                    or width > MAX_DIMENSION
                    or height > MAX_DIMENSION
                    or width * height > MAX_DECODED_PIXELS
                ):
                    raise InvalidImageError()
                decoded.load()
    except AppError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        raise InvalidImageError() from error


async def validate_image(upload: UploadFile) -> ValidatedImage:
    if not upload.filename or upload.content_type not in {"image/jpeg", "image/png"}:
        raise InvalidImageError()

    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise InvalidImageError()

    detected = _detect(content)
    if detected is None or detected[0] != upload.content_type:
        raise InvalidImageError()

    _verify_decode(content)
    return ValidatedImage(
        filename=upload.filename,
        media_type=detected[0],
        provider_format=detected[1],
        content=content,
    )
