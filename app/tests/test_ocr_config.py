import pytest
from pydantic import ValidationError

from app.core.config import Config


def test_ocr_openai_model_defaults_to_supported_project_model():
    settings = Config(_env_file=None)

    assert settings.OPENAI_MODEL == "gpt-4o-mini"


def test_ocr_preprocess_version_defaults_to_v341_and_accepts_the_full_matrix(monkeypatch):
    monkeypatch.delenv("OCR_PREPROCESS_VERSION", raising=False)
    assert Config(_env_file=None).OCR_PREPROCESS_VERSION == "v3.4.1"

    for patch in range(9):
        version = f"v3.1.{patch}"
        assert Config(_env_file=None, OCR_PREPROCESS_VERSION=version).OCR_PREPROCESS_VERSION == version

    for patch in range(1, 9):
        version = f"v3.2.{patch}"
        assert Config(_env_file=None, OCR_PREPROCESS_VERSION=version).OCR_PREPROCESS_VERSION == version
    assert Config(_env_file=None, OCR_PREPROCESS_VERSION="v3.3.1").OCR_PREPROCESS_VERSION == "v3.3.1"


def test_ocr_preprocess_version_rejects_unknown_values():
    with pytest.raises(ValidationError):
        Config(_env_file=None, OCR_PREPROCESS_VERSION="v3.1.9")


@pytest.mark.parametrize("version", ["v3.4.1", "v3.4.2", "v3.4.3"])
def test_adaptive_preprocess_version_is_loaded_from_environment(monkeypatch, version):
    monkeypatch.setenv("OCR_PREPROCESS_VERSION", version)
    settings = Config(_env_file=None)
    assert settings.OCR_PREPROCESS_VERSION == version
