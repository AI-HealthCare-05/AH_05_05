from app.core import config
from app.core.api_timeout import ApiTimeoutMiddleware
from app.core.ocr_upload_middleware import OcrUploadSizeLimitMiddleware
from app.main import app


def test_application_registers_api_timeout_as_outer_middleware():
    middleware_classes = [middleware.cls for middleware in app.user_middleware]

    assert ApiTimeoutMiddleware in middleware_classes
    assert middleware_classes.index(ApiTimeoutMiddleware) < middleware_classes.index(OcrUploadSizeLimitMiddleware)


def test_application_uses_configured_default_and_v1_path_prefix():
    middleware = next(middleware for middleware in app.user_middleware if middleware.cls is ApiTimeoutMiddleware)

    assert middleware.kwargs["router"] is app.router
    assert middleware.kwargs["default_timeout_seconds"] == config.API_TIMEOUT_SECONDS
    assert middleware.kwargs["path_prefix"] == "/api/v1/"
