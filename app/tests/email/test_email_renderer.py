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


def test_user_password_reset_template_uses_approved_copy_and_new_logo() -> None:
    message = EmailTemplateRenderer().render(
        EmailJobPayload(
            template=EmailTemplate.USER_PASSWORD_RESET,
            recipient_email="recipient@example.com",
            temporary_password="Temp1234!",
        )
    )

    assert message.subject == "RxVita 비밀번호 재설정"
    assert "비밀번호 재설정" in message.html_body
    assert "Temp1234!" in message.html_body
    assert "로그인 후 비밀번호를 변경해 주세요." in message.html_body
    assert "관리자 임시비밀번호" not in message.html_body
    assert "님 안녕하세요" not in message.html_body
    assert "시스템 로그인 후" not in message.html_body
    assert message.inline_attachments[0].filename == "rxvita-logo-480.png"


def test_all_email_templates_attach_rxvita_logo_480() -> None:
    renderer = EmailTemplateRenderer()
    payloads = (
        EmailJobPayload(
            template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
            recipient_email="admin@example.com",
            recipient_name="관리자",
            temporary_password="Temp1234!",
        ),
        EmailJobPayload(
            template=EmailTemplate.SIGNUP_VERIFICATION_CODE,
            recipient_email="user@example.com",
            verification_id=1,
            verification_code="123456",
            expires_at=datetime(2026, 9, 7, 3, 1, tzinfo=UTC),
        ),
    )

    for payload in payloads:
        attachment = renderer.render(payload).inline_attachments[0]
        assert attachment.filename == "rxvita-logo-480.png"
        assert attachment.data.startswith(b"\x89PNG")


def test_intake_report_template_renders_safe_korean_markdown() -> None:
    message = EmailTemplateRenderer().render(
        EmailJobPayload(
            template=EmailTemplate.INTAKE_REPORT,
            recipient_email="recipient@example.com",
            report_id="report-20260911-abc123",
            report_markdown=(
                "# 복용약·영양제 AI 보고서\n\n"
                "## 현재 복용 목록\n\n"
                "| 제품명 | 안내 |\n| --- | --- |\n"
                "| 매우 긴 한글 제품명 | [식품안전나라](https://www.foodsafetykorea.go.kr) |\n\n"
                "<script>alert('xss')</script>\n\n"
                "[위험 링크](javascript:alert(1))"
            ),
        )
    )

    assert message.subject == "RxVita 복용약·영양제 AI 보고서"
    assert "복용약·영양제 AI 보고서" in message.text_body
    assert "매우 긴 한글 제품명" in message.html_body
    assert "<table" in message.html_body
    assert 'href="https://www.foodsafetykorea.go.kr"' in message.html_body
    assert "<script>" not in message.html_body
    assert "javascript:" not in message.html_body
    assert "&lt;script&gt;alert" in message.html_body
    assert 'src="cid:rxvita-logo"' in message.html_body


def test_intake_report_plain_text_decodes_literal_entities_once() -> None:
    message = EmailTemplateRenderer().render(
        EmailJobPayload(
            template=EmailTemplate.INTAKE_REPORT,
            recipient_email="recipient@example.com",
            report_id="report-literal-preview",
            report_markdown="# 가상 제품 &#91;검증&#93; &amp;amp; &lt;태그&gt;",
        )
    )
    assert "가상 제품 [검증] &amp; <태그>" in message.text_body
    assert "&#91;" not in message.text_body
    assert "<태그>" not in message.html_body


def test_intake_report_links_preserve_query_encoding_and_do_not_bold_url_contents() -> None:
    message = EmailTemplateRenderer().render(
        EmailJobPayload(
            template=EmailTemplate.INTAKE_REPORT,
            recipient_email="recipient@example.com",
            report_id="report-20260911-link-test",
            report_markdown="[**공식 안내**](https://example.com/docs/**overview**?a=1&b=2)",
        )
    )

    assert 'href="https://example.com/docs/**overview**?a=1&amp;b=2"' in message.html_body
    assert "amp;amp" not in message.html_body
    assert '<a href="https://example.com/docs/**overview**?a=1&amp;b=2"' in message.html_body
    assert "<strong>공식 안내</strong>" in message.html_body


def test_intake_report_rejects_malformed_link_without_failing_render() -> None:
    message = EmailTemplateRenderer().render(
        EmailJobPayload(
            template=EmailTemplate.INTAKE_REPORT,
            recipient_email="recipient@example.com",
            report_id="report-20260911-malformed-link",
            report_markdown="[잘못된 링크](https://[invalid)",
        )
    )

    assert "잘못된 링크" in message.html_body
    assert "https://[invalid" not in message.html_body
