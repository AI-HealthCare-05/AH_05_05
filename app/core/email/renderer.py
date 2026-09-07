from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.email.payload import EmailJobPayload, EmailTemplate
from app.core.email.smtp_sender import EmailMessage, InlineAttachment

ADMIN_TEMPORARY_PASSWORD_SUBJECT = "RxVita 관리자 임시비밀번호"
SIGNUP_VERIFICATION_SUBJECT = "RxVita 회원가입 이메일 인증번호"
LOGO_PATH = Path(__file__).resolve().parents[2] / "static" / "images" / "rxvita-logo-ai-chat-teal.png"


class EmailTemplateRenderer:
    def __init__(self, template_dir: Path | None = None) -> None:
        resolved_dir = template_dir or Path(__file__).resolve().parents[2] / "static" / "templates"
        self._environment = Environment(
            loader=FileSystemLoader(resolved_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render(self, payload: EmailJobPayload) -> EmailMessage:
        if payload.template is EmailTemplate.ADMIN_TEMPORARY_PASSWORD:
            template = self._environment.get_template("emails/admin_temporary_password.html")
            context = {
                "recipient_name": payload.recipient_name,
                "temporary_password": payload.temporary_password,
            }
            return EmailMessage(
                to=str(payload.recipient_email),
                subject=ADMIN_TEMPORARY_PASSWORD_SUBJECT,
                text_body=self._plain_text(
                    recipient_name=payload.recipient_name or "",
                    temporary_password=payload.temporary_password or "",
                ),
                html_body=template.render(**context),
                inline_attachments=(self._logo_attachment(),),
            )
        if payload.template is EmailTemplate.SIGNUP_VERIFICATION_CODE:
            template = self._environment.get_template("emails/signup_verification_code.html")
            code = payload.verification_code or ""
            return EmailMessage(
                to=str(payload.recipient_email),
                subject=SIGNUP_VERIFICATION_SUBJECT,
                text_body=self._signup_verification_plain_text(code),
                html_body=template.render(verification_code=code),
                inline_attachments=(self._logo_attachment(),),
            )
        raise ValueError("지원하지 않는 이메일 템플릿입니다.")

    @staticmethod
    def _logo_attachment() -> InlineAttachment:
        return InlineAttachment(
            content_id="rxvita-logo",
            filename="rxvita-logo.png",
            content_type="image/png",
            data=LOGO_PATH.read_bytes(),
        )

    @staticmethod
    def _plain_text(*, recipient_name: str, temporary_password: str) -> str:
        return (
            f"{recipient_name} 님 안녕하세요.\n\n"
            f"임시비밀번호 : {temporary_password}\n\n"
            "시스템 로그인 후 비밀번호를 변경해 주세요.\n\n"
            "감사합니다.\n"
        )

    @staticmethod
    def _signup_verification_plain_text(verification_code: str) -> str:
        return (
            "RxVita 회원가입 이메일 인증번호입니다.\n\n"
            f"인증번호: {verification_code}\n\n"
            "인증번호는 3분 동안 유효합니다.\n"
            "본인이 요청하지 않았다면 이 메일을 무시해 주세요.\n"
        )
