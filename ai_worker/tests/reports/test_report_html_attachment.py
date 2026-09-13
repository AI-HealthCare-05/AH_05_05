import base64
import hashlib
import json
import re
from datetime import date

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def decrypt_attachment(data: bytes, password: str = "900102") -> str:
    envelope = json.loads(re.search(rb'<script id="report-data" type="application/json">(.*?)</script>', data, re.S)[1])
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), base64.b64decode(envelope["salt"]), envelope["iterations"], 32
    )
    return (
        AESGCM(key).decrypt(base64.b64decode(envelope["iv"]), base64.b64decode(envelope["ciphertext"]), None).decode()
    )


def test_attachment_is_authenticated_encryption_not_hidden_plaintext():
    from app.core.email.report_attachment import encrypt_report_html

    markup = "<!doctype html><h1>비공개 가상 보고서</h1><details><summary>약 정보</summary>가상 효능</details>"
    first = encrypt_report_html(markup, date(1990, 1, 2))
    second = encrypt_report_html(markup, date(1990, 1, 2))
    assert first != second
    assert "비공개 가상 보고서".encode() not in first
    assert b"900102" not in first
    assert decrypt_attachment(first) == markup
    with pytest.raises(InvalidTag):
        decrypt_attachment(first, "900103")
    envelope = json.loads(
        re.search(rb'<script id="report-data" type="application/json">(.*?)</script>', first, re.S)[1]
    )
    corrupted = bytearray(base64.b64decode(envelope["ciphertext"]))
    corrupted[0] ^= 1
    tampered = first.replace(envelope["ciphertext"].encode(), base64.b64encode(corrupted))
    with pytest.raises(InvalidTag):
        decrypt_attachment(tampered)


def test_report_mail_only_contains_instructions_and_an_encrypted_attachment():
    from app.core.email.payload import EmailJobPayload, EmailTemplate
    from app.core.email.renderer import EmailTemplateRenderer

    message = EmailTemplateRenderer().render(
        EmailJobPayload(
            template=EmailTemplate.INTAKE_REPORT,
            recipient_email="example@example.org",
            recipient_name="테스트",
            report_id="synthetic-report",
            report_birth_date=date(1990, 1, 2),
            report_markdown="비공개 복용약 내용",
            report_html="<h1>비공개 복용약 내용</h1>",
        )
    )
    assert "테스트님의 RxVita AI 보고서입니다." in message.text_body
    assert "생년월일 6자리" in message.html_body
    assert "비공개 복용약 내용" not in message.html_body + message.text_body
    assert "900102" not in message.html_body + message.text_body
    assert len(message.attachments) == 1
    assert message.attachments[0].content_type == "text/html"
    assert message.attachments[0].filename.endswith(".html")
    assert "비공개 복용약 내용" in decrypt_attachment(message.attachments[0].data)


def test_report_mail_without_birthdate_fails_closed():
    from app.core.email.payload import EmailJobPayload, EmailTemplate
    from app.core.email.renderer import EmailTemplateRenderer

    with pytest.raises(ValueError, match="생년월일"):
        EmailTemplateRenderer().render(
            EmailJobPayload(
                template=EmailTemplate.INTAKE_REPORT,
                recipient_email="example@example.org",
                report_id="synthetic",
                report_markdown="비공개 내용",
            )
        )


def test_standalone_report_keeps_web_disclosures_and_two_decimal_graph():
    from ai_worker.tests.reports.test_intake_email_parity import sample_email_report
    from app.core.email.intake_report_renderer import render_intake_report_email

    report = sample_email_report()
    report.nutrient_totals[1].amount = "1.6666666666"
    markup, _ = render_intake_report_email(report, standalone=True)
    assert "color:#172033;font-family" in markup
    assert "#145d62" not in markup
    assert "#588181" not in markup
    assert '<details class="registered-products">' in markup
    assert '<details class="medicine">' in markup
    assert "상세 보기" in markup
    assert "성분 포함 제품 1개" in markup
    assert "1.67" in markup
    assert "1.666666" not in markup
    assert 'data-upper-position="88"' in markup
    report.nutrient_totals[0].amount = "2600"
    markup, _ = render_intake_report_email(report, standalone=True)
    assert "width:100.0%;background:#d74444" in markup
    assert 'target="_blank" rel="noopener noreferrer"' in markup
