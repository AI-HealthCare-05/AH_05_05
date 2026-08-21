import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from app.core import config

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10


class EmailSendError(Exception):
    """메일 발송 실패. 호출한 쪽에서 후속 처리를 정한다."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailBackend(ABC):
    """메일 전송 방식. 구현을 갈아끼울 수 있게 인터페이스만 맞춘다.

    SES 등을 추가할 때도 이 클래스를 상속해 state.py 의 선택 분기에 넣으면 된다.
    """

    @abstractmethod
    def send(self, message: EmailMessage) -> None:
        """실패하면 EmailSendError 를 던진다."""


class ConsoleEmailBackend(EmailBackend):
    """개발용. 실제로 보내지 않고 내용을 로그로 출력한다.

    임시 비밀번호 평문이 그대로 찍히므로 로컬 개발에서만 쓴다.
    """

    def send(self, message: EmailMessage) -> None:
        logger.info(
            "[console email]\n  to: %s\n  subject: %s\n  ---\n%s\n  ---",
            message.to,
            message.subject,
            message.body,
        )


class SmtpEmailBackend(EmailBackend):
    """Gmail 등 SMTP 서버로 실제 발송한다.

    본문에 임시 비밀번호가 들어 있으므로 **로그에는 수신자와 제목만 남긴다.**
    """

    def __init__(self, host: str, port: int, user: str, password: str, sender: str) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self.sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(mime)
        except (smtplib.SMTPException, OSError) as err:
            # 예외 메시지에 본문이 섞이지 않도록 타입과 수신자만 남긴다.
            logger.warning("email send failed: to=%s reason=%s", message.to, type(err).__name__)
            raise EmailSendError(str(err)) from err

        logger.info("email sent: to=%s subject=%s", message.to, message.subject)


def build_backend() -> EmailBackend:
    """config.EMAIL_BACKEND 에 따라 구현을 고른다."""
    if config.EMAIL_BACKEND == "smtp":
        missing = [
            name
            for name, value in (
                ("SMTP_HOST", config.SMTP_HOST),
                ("SMTP_USER", config.SMTP_USER),
                ("SMTP_PASSWORD", config.SMTP_PASSWORD),
                ("SMTP_FROM", config.SMTP_FROM),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"EMAIL_BACKEND=smtp 인데 설정이 비어 있습니다: {', '.join(missing)}")

        return SmtpEmailBackend(
            host=config.SMTP_HOST or "",
            port=config.SMTP_PORT,
            user=config.SMTP_USER or "",
            password=config.SMTP_PASSWORD or "",
            sender=config.SMTP_FROM or "",
        )

    return ConsoleEmailBackend()
