import asyncio
import json

import pytest

from ai_worker.reports.v11_plain_language import PlainLanguageRefiner
from ai_worker.schemas.intake_report_cards import (
    CardDetail,
    CardSection,
    IntakeReportCards,
    InteractionCard,
    LifestyleCard,
    MedicationCard,
    OverlapCard,
)


def _cards(*, efficacy: str = "고열을 낮추는 데 사용합니다.") -> IntakeReportCards:
    return IntakeReportCards(
        medications=[
            MedicationCard(
                item_id=101,
                product_name="가상약 A",
                efficacy=CardSection(text=efficacy, source_ids=["guide:1"]),
                caution=CardSection(text="졸릴 수 있으므로 운전 전에 상태를 확인하세요.", source_ids=["guide:1"]),
                contraindication=CardSection(
                    text="이 성분에 알레르기가 있으면 복용하지 마세요.", source_ids=["guide:1"]
                ),
                details=[
                    CardDetail(label="복용 방법", text="1일 2회 복용합니다.", source_ids=["guide:1"]),
                    CardDetail(label="등록 복용 정보", text="아침에 등록했습니다.", source_ids=[]),
                ],
                source_ids=["guide:1"],
            )
        ]
    )


class _Writer:
    def __init__(self, changes: dict[str, str] | None = None) -> None:
        self.changes = changes or {}
        self.payload: dict[str, object] | None = None

    async def ainvoke(self, messages):
        self.payload = json.loads(messages[-1].content)
        return {
            "edits": [
                {"key": field["key"], "text": self.changes.get(field["key"], field["text"])}
                for field in self.payload["fields"]
            ]
        }


class _Reviewer:
    def __init__(self, rejected: set[str] | None = None, *, malformed: bool = False) -> None:
        self.rejected = rejected or set()
        self.malformed = malformed
        self.payload: dict[str, object] | None = None

    async def ainvoke(self, messages):
        self.payload = json.loads(messages[-1].content)
        fields = self.payload["fields"]
        if self.malformed:
            fields = fields[:-1]
        return {
            "reviews": [
                {
                    "key": field["key"],
                    "faithful": field["key"] not in self.rejected,
                    "complete": field["key"] not in self.rejected,
                    "no_new_claims": field["key"] not in self.rejected,
                }
                for field in fields
            ]
        }


@pytest.mark.asyncio
async def test_refine_applies_approved_plain_text_and_retains_only_its_original() -> None:
    cards = _cards()
    key = "medication:101:efficacy"
    writer = _Writer({key: "높은 열을 낮출 때 써요."})

    refined = await PlainLanguageRefiner(writer=writer, reviewer=_Reviewer()).refine(cards)

    medication = refined.medications[0]
    assert medication.efficacy.text == "높은 열을 낮출 때 써요."
    assert medication.caution == cards.medications[0].caution
    assert medication.details[1].text == "아침에 등록했습니다."
    assert [item.model_dump(mode="json", by_alias=True) for item in refined.original_texts] == [
        {
            "key": key,
            "label": "가상약 A · 효능",
            "text": "고열을 낮추는 데 사용합니다.",
            "sourceIds": ["guide:1"],
        }
    ]
    assert all("등록 복용 정보" not in field["label"] for field in writer.payload["fields"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "original,candidate",
    [
        ("하루 2회, 1회 50mg을 복용합니다.", "하루 3회, 1회 50mg을 복용해요."),
        ("비율은 1/2이고 시각은 12:30입니다.", "비율은 2/1이고 시각은 30:12예요."),
        ("&gamma;-GTP 수치를 확인합니다.", "γ-GTP 수치를 확인해요."),
        ("식후 복용합니다.", "[식후 복용](https://example.test)해요."),
    ],
)
async def test_refine_rejects_protected_token_changes_and_new_markup_even_if_reviewer_approves(
    original: str,
    candidate: str,
) -> None:
    cards = _cards(efficacy=original)
    writer = _Writer({"medication:101:efficacy": candidate})

    refined = await PlainLanguageRefiner(writer=writer, reviewer=_Reviewer()).refine(cards)

    assert refined.medications[0].efficacy.text == original
    assert refined.original_texts == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate",
    [
        "이 성분에 알레르기가 있어도 복용해요.",
        "복용 전에 의사와 상담해요.",
    ],
)
async def test_refine_keeps_canonical_when_review_rejects_negation_or_omitted_subject(candidate: str) -> None:
    cards = _cards()
    key = "medication:101:contraindication"
    writer = _Writer({key: candidate})

    refined = await PlainLanguageRefiner(writer=writer, reviewer=_Reviewer({key})).refine(cards)

    assert refined.medications[0].contraindication.text == cards.medications[0].contraindication.text
    assert refined.original_texts == []


@pytest.mark.asyncio
async def test_refine_returns_whole_canonical_payload_for_malformed_review() -> None:
    cards = _cards()
    writer = _Writer({"medication:101:efficacy": "높은 열을 낮출 때 써요."})

    refined = await PlainLanguageRefiner(writer=writer, reviewer=_Reviewer(malformed=True)).refine(cards)

    assert refined == cards


@pytest.mark.asyncio
async def test_refine_returns_canonical_payload_on_timeout() -> None:
    class SlowWriter:
        async def ainvoke(self, _messages):
            await asyncio.sleep(0.05)
            raise AssertionError("cancelled timeout must stop this client")

    cards = _cards()
    refined = await PlainLanguageRefiner(
        writer=SlowWriter(),
        reviewer=_Reviewer(),
        timeout_seconds=0.001,
    ).refine(cards)

    assert refined == cards


@pytest.mark.asyncio
async def test_refine_keeps_identical_shared_actions_consistent() -> None:
    cards = IntakeReportCards(
        interactions=[
            InteractionCard(
                id="i1",
                title="가상 상호작용 1",
                summary="함께 복용할 때 주의합니다.",
                action="복용 전에 전문가에게 확인하세요.",
                source_ids=["source:1"],
                evidence_level="PUBLIC_GUIDE",
                action_level="CHECK",
            )
        ],
        overlaps=[
            OverlapCard(
                nutrient_name="가상 영양소",
                title="가상 중복",
                summary="두 제품에 함께 들어 있습니다.",
                action="복용 전에 전문가에게 확인하세요.",
                product_names=["가상제품 A", "가상제품 B"],
                product_count=2,
                source_ids=["source:2"],
            )
        ],
        lifestyle=[
            LifestyleCard(
                id="l1",
                category="식사",
                title="가상 식사 안내",
                summary="제품 표시를 확인합니다.",
                action="복용 전에 전문가에게 확인하세요.",
                source_ids=["source:3"],
            )
        ],
    )
    writer = _Writer(
        {"interaction:i1:action": "복용 전 전문가에게 확인해요."}
    )

    refined = await PlainLanguageRefiner(writer=writer, reviewer=_Reviewer()).refine(cards)

    assert refined.interactions[0].action == "복용 전 전문가에게 확인해요."
    assert refined.overlaps[0].action == "복용 전 전문가에게 확인해요."
    assert refined.lifestyle[0].action == "복용 전 전문가에게 확인해요."
    writer_action_fields = [field for field in writer.payload["fields"] if field["kind"] == "action"]
    assert len(writer_action_fields) == 1
    assert len([item for item in refined.original_texts if item.text == "복용 전에 전문가에게 확인하세요."]) == 3
