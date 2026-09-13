"""Route-local, bounded in-memory multipart parsing for OCR uploads."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from io import BytesIO
from tempfile import SpooledTemporaryFile
from typing import Annotated, cast

from fastapi import Depends, Request, UploadFile, status
from python_multipart.exceptions import MultipartParseError
from starlette.datastructures import FormData, Headers
from starlette.formparsers import MultiPartException, MultiPartParser, _user_safe_decode, parse_options_header

from app.core.exceptions import AppError
from app.core.ocr_upload_middleware import MAX_OCR_MULTIPART_REQUEST_BYTES
from app.dependencies.security import get_request_user
from app.models.users import User

# The existing request middleware permits 51 MiB. Reserve one MiB for multipart
# framing while retaining a 50 MiB image payload limit.
MAX_OCR_REQUEST_BYTES = MAX_OCR_MULTIPART_REQUEST_BYTES
MAX_OCR_FILE_BYTES = 50 * 1024 * 1024
MAX_OCR_FILES = 1
MAX_OCR_FIELDS = 0
MAX_CONCURRENT_OCR_MEMORY_UPLOADS = 2


class OcrMultipartValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "VALIDATION_ERROR"
    message = "OCR 요청에는 file 이미지 하나만 포함할 수 있습니다."
    field = "file"


class OcrMemoryUploadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "OCR_UPLOAD_TOO_LARGE"
    message = "OCR 요청 크기는 51MB를 초과할 수 없습니다."


class _InMemoryBytesIO(BytesIO):
    """Marks BytesIO as memory-backed for Starlette's UploadFile helpers."""

    _rolled = False


class _RequestTooLarge(MultiPartException):
    pass


class InMemoryOcrMultipartParser(MultiPartParser):
    """Starlette's parser with a BytesIO file sink and OCR-specific limits.

    This mirrors the Starlette 0.50.0 ``on_headers_finished`` implementation,
    replacing only its ``SpooledTemporaryFile`` allocation. Keeping the parser
    route-local avoids changing upload behavior for unrelated endpoints.
    """

    def __init__(self, headers: Headers, stream: AsyncGenerator[bytes, None]) -> None:
        super().__init__(
            headers,
            self._limited_stream(stream),
            max_files=MAX_OCR_FILES,
            max_fields=MAX_OCR_FIELDS,
            max_part_size=MAX_OCR_FILE_BYTES,
        )
        self._file_bytes = 0

    @staticmethod
    async def _limited_stream(stream: AsyncGenerator[bytes, None]) -> AsyncGenerator[bytes, None]:
        received_bytes = 0
        async for chunk in stream:
            received_bytes += len(chunk)
            if received_bytes > MAX_OCR_REQUEST_BYTES:
                raise _RequestTooLarge("OCR request exceeded the maximum size.")
            yield chunk

    def on_part_begin(self) -> None:
        self._file_bytes = 0
        super().on_part_begin()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._file_bytes += end - start
            if self._file_bytes > MAX_OCR_FILE_BYTES:
                raise _RequestTooLarge("OCR file exceeded the maximum size.")
        super().on_part_data(data, start, end)

    def on_headers_finished(self) -> None:
        disposition, options = parse_options_header(self._current_part.content_disposition)
        try:
            self._current_part.field_name = _user_safe_decode(options[b"name"], self._charset)
        except KeyError as error:
            raise MultiPartException('The Content-Disposition header field "name" must be provided.') from error

        if b"filename" not in options:
            self._current_fields += 1
            if self._current_fields > self.max_fields:
                raise MultiPartException(f"Too many fields. Maximum number of fields is {self.max_fields}.")
            self._current_part.file = None
            return

        self._current_files += 1
        if self._current_files > self.max_files:
            raise MultiPartException(f"Too many files. Maximum number of files is {self.max_files}.")
        file = _InMemoryBytesIO()
        # Starlette types this private cleanup list as spool-only. This route's
        # parser deliberately substitutes a BytesIO sink with the same close API.
        self._files_to_close_on_error.append(cast(SpooledTemporaryFile[bytes], file))
        self._current_part.file = UploadFile(
            file=file,
            size=0,
            filename=_user_safe_decode(options[b"filename"], self._charset),
            headers=Headers(raw=self._current_part.item_headers),
        )

    async def parse(self) -> FormData:
        try:
            return await super().parse()
        except BaseException:
            # Starlette itself closes on MultiPartException only. Cancellation
            # must not leave a partially received patient image in memory.
            for file in self._files_to_close_on_error:
                file.close()
            raise


async def _parse_ocr_form(request: Request) -> FormData:
    """Use the request stream once with this endpoint's bounded parser."""

    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "multipart/form-data":
        raise OcrMultipartValidationError()
    return await InMemoryOcrMultipartParser(request.headers, request.stream()).parse()


async def parse_ocr_memory_upload(request: Request) -> UploadFile:
    """Parse and validate the single OCR image without a temporary-file sink."""

    form: FormData | None = None
    try:
        form = await _parse_ocr_form(request)
        upload = form.get("file")
        if len(form) != 1 or not isinstance(upload, UploadFile):
            raise OcrMultipartValidationError()
        return upload
    except _RequestTooLarge as error:
        if form is not None:
            await form.close()
        raise OcrMemoryUploadTooLargeError() from error
    except (MultiPartException, MultipartParseError, OcrMultipartValidationError) as error:
        if form is not None:
            await form.close()
        if isinstance(error, OcrMultipartValidationError):
            raise
        raise OcrMultipartValidationError() from error


async def get_ocr_memory_upload(
    request: Request,
    _user: Annotated[User, Depends(get_request_user)],
) -> AsyncIterator[UploadFile]:
    """Authenticate first, then parse; close the in-memory image on every exit."""

    semaphore = _ocr_memory_upload_semaphore(request)
    async with semaphore:
        upload = await parse_ocr_memory_upload(request)
        try:
            yield upload
        finally:
            await upload.close()


async def get_ocr_preview_memory_slot(
    request: Request,
    _user: Annotated[User, Depends(get_request_user)],
) -> AsyncIterator[None]:
    """Limit authenticated preview byte loads until their responses are sent."""

    async with _ocr_memory_upload_semaphore(request):
        yield


def _ocr_memory_upload_semaphore(request: Request) -> asyncio.Semaphore:
    """Return the current app-loop's admission gate without global state."""

    loop = asyncio.get_running_loop()
    semaphore = getattr(request.app.state, "ocr_memory_upload_semaphore", None)
    semaphore_loop = getattr(request.app.state, "ocr_memory_upload_semaphore_loop", None)
    if not isinstance(semaphore, asyncio.Semaphore) or semaphore_loop is not loop:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_OCR_MEMORY_UPLOADS)
        request.app.state.ocr_memory_upload_semaphore = semaphore
        request.app.state.ocr_memory_upload_semaphore_loop = loop
    return semaphore
