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
    assert all(line in message.text_body for line in approved_lines)
    assert all(line in message.html_body for line in approved_lines)


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
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in message.html_body
