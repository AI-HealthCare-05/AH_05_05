from app.core.config import Config


def test_ocr_openai_model_defaults_to_supported_project_model():
    settings = Config(_env_file=None)

    assert settings.OPENAI_MODEL == "gpt-4o-mini"
