from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.email.payload import EmailJobPayload, EmailTemplate
from app.core.email.smtp_sender import EmailMessage, InlineAttachment

ADMIN_TEMPORARY_PASSWORD_SUBJECT = "RxVita 관리자 임시비밀번호"
USER_PASSWORD_RESET_SUBJECT = "RxVita 비밀번호 재설정"
SIGNUP_VERIFICATION_SUBJECT = "RxVita 회원가입 이메일 인증번호"
LOGO_PATH = Path(__file__).resolve().parents[2] / "static" / "images" / "rxvita-logo-480.png"


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
            expiry = self._format_expiry(payload.expires_in, payload.expires_at)
            return EmailMessage(
                to=str(payload.recipient_email),
                subject=SIGNUP_VERIFICATION_SUBJECT,
                text_body=self._signup_verification_plain_text(code, expiry),
                html_body=template.render(verification_code=code, verification_expiry=expiry),
                inline_attachments=(self._logo_attachment(),),
            )
        if payload.template is EmailTemplate.USER_PASSWORD_RESET:
            template = self._environment.get_template("emails/user_password_reset.html")
            temporary_password = payload.temporary_password or ""
            return EmailMessage(
                to=str(payload.recipient_email),
                subject=USER_PASSWORD_RESET_SUBJECT,
                text_body=self._user_password_reset_plain_text(temporary_password),
                html_body=template.render(temporary_password=temporary_password),
                inline_attachments=(self._logo_attachment(),),
            )
        raise ValueError("지원하지 않는 이메일 템플릿입니다.")

    @staticmethod
    def _logo_attachment() -> InlineAttachment:
        return InlineAttachment(
            content_id="rxvita-logo",
            filename="rxvita-logo-480.png",
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
    def _signup_verification_plain_text(verification_code: str, verification_expiry: str) -> str:
        return (
            "RxVita 회원가입 이메일 인증번호입니다.\n\n"
            f"인증번호: {verification_code}\n\n"
            f"인증번호는 {verification_expiry} 유효합니다.\n"
            "본인이 요청하지 않았다면 이 메일을 무시해 주세요.\n"
        )

    @staticmethod
    def _format_duration(seconds: int) -> str:
        if seconds % 60 == 0:
            return f"{seconds // 60}분"
        return f"{seconds}초"

    @classmethod
    def _format_expiry(cls, expires_in: int | None, expires_at: datetime | None) -> str:
        if expires_in is not None:
            return f"{cls._format_duration(expires_in)} 동안"
        if expires_at is None:
            raise ValueError("회원가입 이메일 인증 만료시각이 누락되었습니다.")
        timezone_name = expires_at.tzname()
        timezone_suffix = f" {timezone_name}" if timezone_name else ""
        return (
            f"{expires_at.year}년 {expires_at.month}월 {expires_at.day}일 "
            f"{expires_at.hour:02d}:{expires_at.minute:02d}{timezone_suffix}까지"
        )

    @staticmethod
    def _user_password_reset_plain_text(temporary_password: str) -> str:
        return (
            "비밀번호 재설정\n\n"
            f"임시비밀번호 : {temporary_password}\n\n"
            "로그인 후 비밀번호를 변경해 주세요.\n\n"
            "감사합니다.\n"
        )
