from app.models.enums import BackgroundJobType


def test_email_is_a_supported_background_job_type() -> None:
    assert BackgroundJobType("EMAIL") is BackgroundJobType.EMAIL
