from app.core.email.payload import EmailJobPayload, EmailTemplate
from app.core.email.renderer import EmailTemplateRenderer


def test_admin_temporary_password_template_renders_approved_text_and_html() -> None:
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
    assert message.subject == "[RxVita] 임시비밀번호 안내"
    assert all(line in message.text_body for line in approved_lines)
    assert all(line in message.html_body for line in approved_lines[1:])
    assert "<strong>홍길동</strong> 님 안녕하세요." in message.html_body
    assert "#e8f9f7" in message.html_body
    assert "#0b7f75" in message.html_body
    assert "#06356f" in message.html_body
    assert "#f0f5ff" not in message.html_body
    assert "#1746a2" not in message.html_body


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
