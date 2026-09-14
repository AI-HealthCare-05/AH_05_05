"""Offline email projection checks; no app test bootstrap, DB or SMTP."""

import base64
from datetime import date
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from ai_worker.schemas.intake_report import IntakeReportResult
from ai_worker.tests.reports.test_report_html_attachment import decrypt_attachment
from app.dtos.intake_reports import IntakeReportResponse


def sample_email_report() -> IntakeReportResponse:
    data = IntakeReportResponse.from_result(IntakeReportResult.empty(user_id=1)).model_dump()
    data.update(
        report_status="PARTIAL",
        presentation_version="ai-report-v11",
        profile_label="40세 남성",
        basis_note="표시된 값은 등록한 1회 복용량과 하루 복용 횟수를 제품 라벨 함량에 반영한 합계입니다.",
        current_stack=[
            dict(
                item_type="MEDICATION",
                item_id=1,
                product_name="등록한 약",
                registered_intake_info="1.00 · 1일 1회",
                scheduled_slots=[],
                evidence_level="REGISTERED_INTAKE",
            ),
            dict(
                item_type="SUPPLEMENT",
                item_id=2,
                product_name="등록한 영양제",
                ingredient_summary="칼슘 600mg · 비타민 D 33μg",
                registered_intake_info="1.50정",
                scheduled_slots=[],
                evidence_level="REGISTERED_INTAKE",
            ),
        ],
        nutrient_totals=[
            dict(
                nutrient_name="칼슘",
                daily_total="600mg",
                amount="600.00",
                unit="mg",
                reference_value="800",
                reference_kind="RNI",
                reference_percent="75",
                upper_limit_value="2500",
                included_product_names=["등록한 영양제"],
                unknown_product_names=["합산 제외 테스트 제품"],
                calculation_status="CALCULATED",
            ),
            dict(
                nutrient_name="비타민 D",
                daily_total="33μg",
                amount="33",
                unit="μg",
                reference_value="10",
                reference_kind="AI",
                reference_percent="330",
                upper_limit_value="100",
                included_product_names=[],
                calculation_status="CALCULATED",
            ),
            dict(
                nutrient_name="비타민 A",
                daily_total="700μg RAE",
                amount="700",
                unit="μg RAE",
                reference_value="800",
                reference_kind="RNI",
                upper_limit_note="성분 형태별 상한 기준이 달라 비교하지 않았어요.",
                included_product_names=[],
                calculation_status="CALCULATED",
            ),
            dict(
                nutrient_name="나트륨",
                daily_total="0mg",
                amount="0",
                unit="mg",
                included_product_names=[],
                calculation_status="CALCULATED",
            ),
        ],
        cards=dict(
            medications=[
                dict(
                    item_id=1,
                    product_name="등록한 약",
                    efficacy=dict(text="제품 안내의 효능입니다."),
                    caution=dict(text="제품 안내의 주의사항입니다."),
                    contraindication=dict(text="제품 안내의 금기입니다."),
                    details=[],
                    source_ids=[],
                )
            ],
            interactions=[
                dict(
                    id="pair-1",
                    title="첫 번째 조합",
                    summary="확인된 상호작용 원문입니다.",
                    action="같은 안내",
                    evidence_level="APPROVED_RULE",
                    action_level="WARNING",
                ),
                dict(
                    id="pair-2",
                    title="두 번째 조합",
                    summary="두 번째 원문입니다.",
                    action="같은 안내",
                    evidence_level="APPROVED_RULE",
                    action_level="WARNING",
                ),
            ],
            overlaps=[],
            lifestyle=[
                dict(
                    id="time-1",
                    category="복용 시점",
                    title="복용 시간 안내",
                    summary="식사와 함께 먹는 안내입니다.",
                    action="식사 시간에 맞춰 드시는 걸 추천해요.",
                )
            ],
            sources=[
                dict(id="s-1", title="공식 출처", url="https://example.org/info?a=1&b=2", evidence_level="PUBLIC_GUIDE")
            ],
        ),
        unverified_items=[
            dict(
                item_type="AMBIGUOUS_PRODUCT",
                title="제품명 확인 필요",
                message="확정하지 못한 제품이 있습니다.",
                related_items=[],
                next_step="제품명을 확인해 주세요.",
            )
        ],
    )
    data["data_availability"].update(active_medication_count=1, active_supplement_count=1)
    return IntakeReportResponse.model_validate(data)


@pytest.mark.parametrize("standalone", [False, True])
def test_email_groups_unavailable_medications_without_empty_details(standalone):
    from app.core.email.intake_report_renderer import render_intake_report_email

    data = sample_email_report().model_dump()
    missing = {**data["cards"]["medications"][0], "item_id": 99, "product_name": "스토엠정", "has_information": False}
    data["cards"]["medications"].append(missing)
    markup, plain = render_intake_report_email(IntakeReportResponse.model_validate(data), standalone=standalone)
    assert "확인 불가 약품" in plain
    assert "스토엠정" in plain
    assert "확인 불가 약품" in markup
    assert markup.count('<details class="medicine">') == (1 if standalone else 0)


def test_email_uses_web_card_order_and_values_without_old_percent_or_exclusions():
    from app.core.email.intake_report_renderer import render_intake_report_email

    report = sample_email_report()
    rendered = render_intake_report_email(report)
    assert rendered is not None
    markup, plain = rendered
    headings = [
        "약·영양제 리포트",
        "함께 확인할 주의사항",
        "생활습관 가이드",
        "영양제 성분 합계",
        "약 정보",
        "확인하지 못한 정보",
        "비교 기준과 출처",
    ]
    assert [plain.index(title) for title in headings] == sorted(plain.index(title) for title in headings)
    assert "나트륨" not in markup
    assert "합산 제외 테스트 제품" not in markup
    assert "75%" not in plain and "330%" not in plain
    assert "칼슘" in plain and "600" in plain and "2,500" in plain
    assert 'data-upper-position="80"' in markup
    assert "공통 안내 · 2개 항목" in plain and plain.count("같은 안내") == 1
    assert "등록한 약" in plain and "등록한 영양제" in plain
    assert "칼슘 600mg · 비타민 D 33μg" in plain
    assert "1 · 1일 1회" not in plain and "1.5정" not in plain and "1.00" not in plain
    assert "성분 형태별 상한 기준이 달라 비교하지 않았어요." in plain
    assert "40세 남성" in plain and "상한은 섭취 목표가 아닙니다." in plain
    assert "<details" not in markup and "<script" not in markup


def test_email_escapes_evidence_and_filters_source_urls_without_decoding_twice():
    from app.core.email.intake_report_renderer import render_intake_report_email

    data = sample_email_report().model_dump()
    data["cards"]["medications"][0]["efficacy"]["text"] = "&lt;img src=x onerror=alert(1)&gt; &amp;lt;태그&amp;gt;"
    data["cards"]["sources"][0]["url"] = "javascript:alert(1)"
    markup, plain = render_intake_report_email(IntakeReportResponse.model_validate(data))
    assert "<img src=x" not in markup and "onerror=" not in markup.replace("&lt;img src=x onerror=alert(1)&gt;", "")
    assert "javascript:" not in markup
    assert "&amp;lt;태그&amp;gt;" in markup
    assert "&lt;태그&gt;" in plain


def test_email_html_survives_encrypted_snapshot_and_worker_renderer():
    from app.core.email.intake_report_renderer import render_intake_report_email
    from app.core.email.payload import EmailJobPayload, EmailPayloadCodec, EmailTemplate
    from app.core.email.renderer import EmailTemplateRenderer
    from app.services.intake_report_email import IntakeReportEmailService

    markup, plain = render_intake_report_email(sample_email_report())
    key = Fernet.generate_key().decode()
    user = SimpleNamespace(id=3, email="owner@example.org")
    service = IntakeReportEmailService(encryption_key=key)
    token = service.create_snapshot_token(user=user, report_markdown=plain, report_html=markup)
    snapshot = service.consume_snapshot_token(token=token, user=user)
    codec = EmailPayloadCodec(key)
    payload = codec.decrypt(
        codec.encrypt(
            EmailJobPayload(
                template=EmailTemplate.INTAKE_REPORT,
                recipient_email=user.email,
                report_id=snapshot.report_id,
                report_markdown=snapshot.report_markdown,
                report_html=snapshot.report_html,
                report_birth_date=date(1990, 1, 2),
            )
        )
    )
    message = EmailTemplateRenderer().render(payload)
    assert (
        decrypt_attachment(message.attachments[0].data).replace(
            "data:image/png;base64," + base64.b64encode(message.inline_attachments[0].data).decode(),
            "cid:rxvita-logo",
        )
        == markup
    )
    assert "영양제 성분 합계" not in message.text_body + message.html_body
    assert len(message.inline_attachments) == 1


def test_report_ids_stay_out_of_subjects_without_altering_html():
    from app.core.email.intake_report_renderer import render_intake_report_email
    from app.core.email.payload import EmailJobPayload, EmailTemplate
    from app.core.email.renderer import EmailTemplateRenderer

    markup, plain = render_intake_report_email(sample_email_report())
    renderer = EmailTemplateRenderer()
    messages = [
        renderer.render(
            EmailJobPayload(
                template=EmailTemplate.INTAKE_REPORT,
                recipient_email="owner@example.org",
                report_id=report_id,
                report_markdown=plain,
                report_html=markup,
                report_birth_date=date(1990, 1, 2),
            )
        )
        for report_id in ["report-one", "report-two", "report-one"]
    ]
    assert all("report-one" not in message.subject and "report-two" not in message.subject for message in messages)
    assert all("영양제 성분 합계" in decrypt_attachment(message.attachments[0].data) for message in messages)
    assert all("영양제 성분 합계" not in message.html_body + message.text_body for message in messages)


@pytest.mark.parametrize("upper", [None, "0", "NaN", "500"])
def test_email_does_not_invent_an_invalid_upper_limit(upper):
    from app.core.email.intake_report_renderer import render_intake_report_email

    report = sample_email_report()
    report.nutrient_totals = [report.nutrient_totals[0].model_copy(update={"upper_limit_value": upper})]
    markup, plain = render_intake_report_email(report)
    assert "data-upper-position" not in markup
    assert "상한 기준을 확인할 수 없어요." in plain


def test_legacy_report_keeps_existing_markdown_path():
    from app.core.email.intake_report_renderer import render_intake_report_email

    assert render_intake_report_email(IntakeReportResponse.from_result(IntakeReportResult.empty(user_id=1))) is None


async def test_generation_to_send_endpoint_to_encrypted_background_task_keeps_web_snapshot(monkeypatch):
    from app.apis.v1.intake_report_router import generate_intake_report, send_intake_report_email
    from app.core.email.payload import EmailPayloadCodec
    from app.core.email.renderer import EmailTemplateRenderer
    from app.dtos.intake_reports import GenerateIntakeReportRequest, SendIntakeReportEmailRequest
    from app.models.background_jobs import BackgroundJob
    from app.services.email_jobs import EmailJobService
    from app.services.intake_report_email import IntakeReportEmailService

    web = sample_email_report()
    data = IntakeReportResult.empty(user_id=1).model_dump()
    fields = web.model_dump()
    data.update({key: value for key, value in fields.items() if key in data and key != "executive_summary"})
    data["status"] = "PARTIAL"
    result = IntakeReportResult.model_validate(data)
    user = SimpleNamespace(id=3, email="owner@example.org", name="테스트", birth_date=date(1990, 1, 2))
    key = Fernet.generate_key().decode()
    codec = EmailPayloadCodec(key)

    class ReportService:
        async def generate(self, *, user):
            return result

    class VerifiedEmailService(IntakeReportEmailService):
        async def require_verified_recipient(self, *, user):
            return user.email  # Authentication/verification DB boundary only.

    class Scheduler:
        job_id = None

        def schedule(self, job_id):
            self.job_id = job_id

    created = {}

    async def create_job(**kwargs):
        job = SimpleNamespace(id=42, encrypted_payload=None, next_attempt_at=None, updated_at=None, **kwargs)

        async def save(*, update_fields):
            return None

        job.save = save
        created["job"] = job
        return job

    monkeypatch.setattr(BackgroundJob, "create", create_job)
    scheduler = Scheduler()
    service = VerifiedEmailService(encryption_key=key)
    response = await generate_intake_report(
        data=GenerateIntakeReportRequest(), user=user, service=ReportService(), email_service=service
    )
    await send_intake_report_email(
        data=SendIntakeReportEmailRequest(email_token=response.email_token),
        user=user,
        email_service=service,
        email_job_service=EmailJobService(codec=codec),
        scheduler=scheduler,
    )
    assert scheduler.job_id == 42
    payload = codec.decrypt(created["job"].encrypted_payload)
    message = EmailTemplateRenderer().render(payload)
    attachment_html = decrypt_attachment(message.attachments[0].data)
    assert "영양제 성분 합계" in attachment_html
    assert "data-upper-position" in attachment_html
    assert "영양제 성분 합계" not in message.html_body
    assert "75%" not in message.text_body
    assert response.cards == result.cards
    assert payload.recipient_email == user.email
    assert payload.report_birth_date == user.birth_date
    assert payload.recipient_name == user.name


def test_html_snapshot_preserves_recipient_binding_and_old_tokens():
    from app.core.email.intake_report_renderer import render_intake_report_email
    from app.services.intake_report_email import IntakeReportEmailService, IntakeReportEmailTokenError

    service = IntakeReportEmailService(encryption_key=Fernet.generate_key().decode())
    owner = SimpleNamespace(id=1, email="owner@example.org")
    markup, plain = render_intake_report_email(sample_email_report())
    token = service.create_snapshot_token(user=owner, report_markdown=plain, report_html=markup)
    with pytest.raises(IntakeReportEmailTokenError):
        service.consume_snapshot_token(token=token, user=SimpleNamespace(id=2, email=owner.email))
    with pytest.raises(IntakeReportEmailTokenError):
        service.consume_snapshot_token(token=token, user=SimpleNamespace(id=1, email="changed@example.org"))
    tampered = token[:50] + ("A" if token[50] != "A" else "B") + token[51:]
    with pytest.raises(IntakeReportEmailTokenError):
        service.consume_snapshot_token(token=tampered, user=owner)
    legacy = service.create_snapshot_token(user=owner, report_markdown="# 기존 보고서")
    snapshot = service.consume_snapshot_token(token=legacy, user=owner)
    assert snapshot.report_html is None and snapshot.report_markdown == "# 기존 보고서"


def test_email_send_request_cannot_supply_html_or_recipient():
    from pydantic import ValidationError

    from app.dtos.intake_reports import SendIntakeReportEmailRequest

    with pytest.raises(ValidationError):
        SendIntakeReportEmailRequest(
            email_token="signed", report_html="<script>bad</script>", recipient_email="other@example.org"
        )


def test_email_visible_notice_and_long_evidence_are_never_truncated():
    from app.core.email.intake_report_renderer import render_intake_report_email

    data = sample_email_report().model_dump()
    notice = "‘등록한 약’을 ‘제품명’으로 추정한 제품 안내입니다."
    long_text = "제품 안내의 긴 원문입니다. " * 500 + "마지막 문장 0.005mg"
    data["cards"]["medications"][0]["identity_notice"] = notice
    data["cards"]["medications"][0]["caution"]["text"] = long_text
    markup, plain = render_intake_report_email(IntakeReportResponse.model_validate(data))
    assert notice in plain
    assert plain.index(notice) < plain.index("제품 안내의 효능입니다.")
    assert long_text in plain
    assert "마지막 문장 0.005mg" in markup


def test_email_preserves_over_upper_and_no_reference_but_omits_unknown_totals():
    from app.core.email.intake_report_renderer import render_intake_report_email

    report = sample_email_report()
    report.nutrient_totals[0].amount = "4000"
    report.nutrient_totals[1].amount = None
    report.nutrient_totals[2].reference_value = None
    markup, plain = render_intake_report_email(report)
    assert "4,000" in plain and "상한 초과" in plain
    assert "미확인" not in plain
    assert "비교 기준 없음 · 확인된 합계만 표시했어요." in plain
    assert 'width="100.0%"' not in markup  # Threshold segments retained even when current amount overflows.


def test_email_rejects_non_displayable_numeric_magnitude_like_the_web():
    from app.core.email.intake_report_renderer import render_intake_report_email

    report = sample_email_report()
    report.nutrient_totals = [report.nutrient_totals[0].model_copy(update={"amount": "1e999999"})]
    markup, plain = render_intake_report_email(report)
    assert "미확인" not in plain
    assert "data-upper-position" not in markup
    assert len(markup) < 50_000


def test_email_snapshot_never_emits_a_token_that_exceeds_the_send_contract():
    from app.services.intake_report_email import IntakeReportEmailService

    service = IntakeReportEmailService(encryption_key=Fernet.generate_key().decode())
    user = SimpleNamespace(id=1, email="owner@example.org")
    assert service.create_snapshot_token(user=user, report_markdown="내용", report_html="가" * 400_001) is None
    assert service.create_snapshot_token(user=user, report_markdown="내용", report_html="😀" * 190_000) is None


def test_email_omits_registered_intake_details_but_keeps_product_and_ingredient_data():
    from app.core.email.intake_report_renderer import render_intake_report_email

    data = sample_email_report().model_dump()
    data["cards"]["medications"][0]["details"] = [
        {"label": "등록한 복용 정보", "text": "1.00정 · 아침", "source_ids": []},
        {"label": "이상 반응", "text": "기존 상세 원문", "source_ids": []},
        {"label": "등록한 계획", "text": "0.50정 · 저녁", "source_ids": []},
    ]
    markup, plain = render_intake_report_email(IntakeReportResponse.model_validate(data))

    for rendered in (markup, plain):
        assert "사용자가 등록한 복용 정보" not in rendered
        assert "1.00정 · 아침" not in rendered
        assert "0.50정 · 저녁" not in rendered
        assert "1.50정" not in rendered
        assert "등록한 약" in rendered
        assert "등록한 영양제" in rendered
        assert "칼슘 600mg · 비타민 D 33μg" in rendered
        assert "기존 상세 원문" in rendered
