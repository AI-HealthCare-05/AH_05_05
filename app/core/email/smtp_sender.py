import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str


class EmailDeliveryError(Exception):
    def __init__(self, code: str, *, retryable: bool):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self.from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)
        mime.add_alternative(message.html_body, subtype="html")

        try:
            with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(mime)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailDeliveryError("EMAIL_AUTH_FAILED", retryable=False) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise EmailDeliveryError("EMAIL_RECIPIENT_REJECTED", retryable=False) from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise EmailDeliveryError("EMAIL_SMTP_TEMPORARY_ERROR", retryable=True) from exc
            raise EmailDeliveryError("EMAIL_SMTP_PERMANENT_ERROR", retryable=False) from exc
        except (OSError, TimeoutError) as exc:
            raise EmailDeliveryError("EMAIL_CONNECTION_ERROR", retryable=True) from exc
        except smtplib.SMTPException as exc:
            raise EmailDeliveryError("EMAIL_SMTP_PERMANENT_ERROR", retryable=False) from exc

        logger.info("email sent: to=%s subject=%s", message.to, message.subject)
