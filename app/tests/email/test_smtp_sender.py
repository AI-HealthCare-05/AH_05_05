import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.core.email.smtp_sender import EmailDeliveryError, EmailMessage, SmtpEmailSender


def sender() -> SmtpEmailSender:
    return SmtpEmailSender(
        host="smtp.example.com",
        port=587,
        username="sender@example.com",
        password="app-password",
        from_address="sender@example.com",
    )


def message() -> EmailMessage:
    return EmailMessage(
        to="recipient@example.com",
        subject="임시비밀번호 안내",
        text_body="평문 본문",
        html_body="<html><body><strong>HTML 본문</strong></body></html>",
    )


def test_smtp_sender_sends_multipart_alternative_message() -> None:
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp

    with patch("app.core.email.smtp_sender.smtplib.SMTP", return_value=smtp):
        sender().send(message())

    smtp.starttls.assert_called_once_with()
    smtp.login.assert_called_once_with("sender@example.com", "app-password")
    sent = smtp.send_message.call_args.args[0]
    assert sent["From"] == "sender@example.com"
    assert sent["To"] == "recipient@example.com"
    assert sent.get_body(preferencelist=("plain",)).get_content().strip() == "평문 본문"
    assert "<strong>HTML 본문</strong>" in sent.get_body(preferencelist=("html",)).get_content()


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_retryable"),
    [
        (OSError("connection failed"), "EMAIL_CONNECTION_ERROR", True),
        (smtplib.SMTPResponseException(421, b"try later"), "EMAIL_SMTP_TEMPORARY_ERROR", True),
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), "EMAIL_AUTH_FAILED", False),
        (
            smtplib.SMTPRecipientsRefused({"recipient@example.com": (550, b"rejected")}),
            "EMAIL_RECIPIENT_REJECTED",
            False,
        ),
        (smtplib.SMTPResponseException(550, b"permanent"), "EMAIL_SMTP_PERMANENT_ERROR", False),
    ],
)
def test_smtp_sender_classifies_failures(
    failure: Exception,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    with (
        patch("app.core.email.smtp_sender.smtplib.SMTP", side_effect=failure),
        pytest.raises(EmailDeliveryError) as error,
    ):
        sender().send(message())

    assert error.value.code == expected_code
    assert error.value.retryable is expected_retryable
    assert "app-password" not in str(error.value)
    assert "평문 본문" not in str(error.value)
