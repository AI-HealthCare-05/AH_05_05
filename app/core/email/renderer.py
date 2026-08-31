from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.email.payload import EmailJobPayload, EmailTemplate
from app.core.email.smtp_sender import EmailMessage

ADMIN_TEMPORARY_PASSWORD_SUBJECT = "[Ozcoding AI Health] 임시비밀번호 안내"


class EmailTemplateRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        resolved_dir = template_dir or Path(__file__).resolve().parents[2] / "static" / "templates"
        self._environment = Environment(
            loader=FileSystemLoader(resolved_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render(self, payload: EmailJobPayload) -> EmailMessage:
        if payload.template is not EmailTemplate.ADMIN_TEMPORARY_PASSWORD:
            raise ValueError("지원하지 않는 이메일 템플릿입니다.")
        template = self._environment.get_template("emails/admin_temporary_password.html")
        context = {
            "recipient_name": payload.recipient_name,
            "temporary_password": payload.temporary_password,
        }
        return EmailMessage(
            to=str(payload.recipient_email),
            subject=ADMIN_TEMPORARY_PASSWORD_SUBJECT,
            text_body=self._plain_text(**context),
            html_body=template.render(**context),
        )

    @staticmethod
    def _plain_text(*, recipient_name: str, temporary_password: str) -> str:
        return (
            f"{recipient_name} 님 안녕하세요.\n\n"
            f"임시비밀번호 : {temporary_password}\n\n"
            "시스템 로그인 후 비밀번호를 변경해 주세요.\n\n"
            "감사합니다.\n"
        )
