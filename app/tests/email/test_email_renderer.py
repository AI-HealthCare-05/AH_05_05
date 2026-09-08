from datetime import UTC, datetime

from app.core.email.payload import EmailJobPayload, EmailTemplate
from app.core.email.renderer import EmailTemplateRenderer


def test_admin_temporary_password_template_renders_plain_colored_password_without_expiry_notice() -> None:
    renderer = EmailTemplateRenderer()
    payload = EmailJobPayload(
        template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
        recipient_email="recipient@example.com",
        recipient_name="홍길동",
        temporary_password="Temp1234!",
    )

    message = renderer.render(payload)

    approved_lines = (
        "홍길동 님 안녕하세요.",
        "임시비밀번호 : Temp1234!",
        "시스템 로그인 후 비밀번호를 변경해 주세요.",
        "감사합니다.",
    )
    assert message.to == "recipient@example.com"
    assert message.subject == "RxVita 관리자 임시비밀번호"
    assert all(line in message.text_body for line in approved_lines)
    assert 'src="cid:rxvita-logo"' in message.html_body
    assert "관리자 임시비밀번호" in message.html_body
    assert 'class="temporary-password"' in message.html_body
    assert "Temp1234!" in message.html_body
    assert "font-size:20px" in message.html_body
    assert "color:#0b7f75" in message.html_body
    assert 'class="temporary-password-character"' not in message.html_body
    assert "시스템 로그인 후 비밀번호를 변경해 주세요." in message.html_body
    assert "본인이 요청하지 않았다면 이 메일을 무시해 주세요." not in message.html_body
    assert "<strong>홍길동</strong> 님 안녕하세요." in message.html_body
    assert [attachment.content_id for attachment in message.inline_attachments] == ["rxvita-logo"]
    assert message.inline_attachments[0].content_type == "image/png"
    assert message.inline_attachments[0].data.startswith(b"\x89PNG")


def test_admin_temporary_password_template_escapes_recipient_name() -> None:
    renderer = EmailTemplateRenderer()
    payload = EmailJobPayload(
        template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
        recipient_email="recipient@example.com",
        recipient_name="<script>alert(1)</script>",
        temporary_password="Temp1234!",
    )

    message = renderer.render(payload)

    assert "<script>" not in message.html_body
    assert "<strong>&lt;script&gt;alert(1)&lt;/script&gt;</strong>" in message.html_body


def test_signup_verification_template_renders_six_code_cells_and_inline_logo() -> None:
    message = EmailTemplateRenderer().render(
        EmailJobPayload(
            template=EmailTemplate.SIGNUP_VERIFICATION_CODE,
            recipient_email="recipient@example.com",
            verification_id=17,
            verification_code="012345",
            expires_in=60,
            expires_at=datetime(2026, 9, 7, 3, 1, tzinfo=UTC),
        )
    )

    assert message.subject == "RxVita 회원가입 이메일 인증번호"
    assert "인증번호: 012345" in message.text_body
    assert "1분 동안 유효" in message.text_body
    assert "3분 동안 유효" not in message.text_body
    assert 'src="cid:rxvita-logo"' in message.html_body
    assert message.html_body.count('class="verification-digit"') == 6
    assert "1분 동안 유효" in message.html_body
    assert "3분 동안 유효" not in message.html_body
    assert [attachment.content_id for attachment in message.inline_attachments] == ["rxvita-logo"]
    assert message.inline_attachments[0].content_type == "image/png"
    assert message.inline_attachments[0].data.startswith(b"\x89PNG")
