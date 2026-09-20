import pytest

from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.llm.generators.medication_answer_generator import (
    OpenAIMedicationAnswerGenerator,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.evidence_reasoning import EvidenceReasoningOutput
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationAnswerFallbackReason,
    MedicationAnswerRewriteStatus,
    MedicationChatAnswerDomain,
    MedicationChatReasonCode,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRiskDecision,
    MedicationChatRiskScope,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
    MedicationEvidenceCoverage,
)
from ai_worker.schemas.medication_search import MedicationSearchExecutionObservation


class FakeAnswerClient:
    def __init__(self, response=None, responses: list | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.responses = list(responses or [])
        self.error = error
        self.messages = None
        self.all_messages = []

    async def ainvoke(self, messages):
        self.messages = messages
        self.all_messages.append(messages)
        if self.error is not None:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return self.response


def build_request() -> MedicationChatRequest:
    return MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀정500밀리그람 주의사항을 알려줘",
    )


def build_result() -> MedicationChatResult:
    return MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer=("일반 제품 안내\n- 정해진 용법을 지킵니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."),
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        sources=[
            MedicationChatSource(
                kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                title="e약은요 · 타이레놀정500밀리그람",
                medication_guide_id=12,
            )
        ],
        prompt_version="medication-chat-prompt-v1",
        schema_version="medication-chat-result-v1",
    )


async def test_generator_rewrites_draft_and_preserves_grounding_metadata() -> None:
    client = FakeAnswerClient(
        response={"answer": ("정해진 용법을 지켜 복용해야 합니다. 이 안내는 의료진의 진료를 대체하지 않습니다.")}
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=client,
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=build_result(),
    )

    assert outcome.result.answer.startswith("정해진 용법")
    assert outcome.result.sources == build_result().sources
    assert outcome.result.model_name == "gpt-4o-mini"
    assert outcome.result.prompt_version == "medication-chat-prompt-v9"
    assert outcome.observation.status == MedicationAnswerRewriteStatus.REWRITTEN
    assert outcome.observation.fallback_used is False
    assert outcome.observation.fallback_reason is None
    assert client.messages is not None


async def test_generator_repairs_an_overlong_bullet_once() -> None:
    client = FakeAnswerClient(
        responses=[
            {
                "answer": (
                    "⚠️ **주의사항**\n- 이 문장은 원문을 그대로 옮긴 매우 긴 주의사항으로 "
                    "사용자가 휴대폰 화면에서 빠르게 읽기 어려운 내용을 포함합니다."
                ),
                "section_types": ["CAUTION"],
            },
            {
                "answer": "⚠️ **주의사항**\n- 정기적 음주 시 의료진과 상담하세요.",
                "section_types": ["CAUTION"],
            },
        ]
    )
    result = build_result().model_copy(
        update={
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            )
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert outcome.result.answer == "⚠️ **주의사항**\n- 정기적 음주 시 의료진과 상담하세요."
    assert len(client.all_messages) == 2
    assert "형식 보정" in str(client.all_messages[-1])
    assert "공식 복용 중단·상담 지시는 초안 표현을 그대로 보존" in str(client.all_messages[-1])


@pytest.mark.parametrize("repair_succeeds", [True, False])
@pytest.mark.parametrize("keeps_empty_headers", [True, False])
async def test_generator_preserves_evidenced_overview_when_model_returns_no_evidence(
    repair_succeeds: bool, keeps_empty_headers: bool
) -> None:
    draft = (
        "💊 **복약정보**\n\n- 와파린\n\n💪🏻 **영양제 정보**\n\n- 비타민 D\n\n---\n\n"
        "🧬 **약과 상호작용**\n\n"
        "- 메나테트레논은 와파린의 항응고 효과를 감소시킬 수 있습니다.\n"
        "- 이그라티모드는 와파린의 작용을 증대시킬 수 있습니다.\n\n"
        "🍗 **그 외 상호작용**\n\n"
        "- 녹차·홍차·우롱차의 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다."
    )
    missing = (
        "💊 **복약정보**\n\n- 와파린\n\n💪🏻 **영양제 정보**\n\n- 비타민 D\n\n---\n\n"
        "🔁 **복약정보와 상호작용**\n\n"
        "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 못했습니다.\n"
        "- 확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다."
    )
    if keeps_empty_headers:
        missing = (
            "🧬 **약과 상호작용**\n\n- 현재 근거에서는 해당 조합을 확인하지 못했습니다.\n\n🍗 **그 외 상호작용**\n"
        )
    client = FakeAnswerClient(
        responses=[
            {"answer": missing, "section_types": ["INTERACTION"]},
            {"answer": draft if repair_succeeds else missing, "section_types": ["INTERACTION"]},
        ]
    )
    result = build_result().model_copy(
        update={
            "answer": draft,
            "route": MedicationChatRoute.ACTIVE_INTAKE,
            "sources": [
                MedicationChatSource(
                    kind=MedicationChatSourceKind.INTERACTION_RULE,
                    title="승인된 상호작용 규칙",
                    interaction_rule_id=1,
                )
            ],
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.INTERACTION],
                covered_section_types=[KnowledgeSectionType.INTERACTION],
            ),
        }
    )
    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request().model_copy(update={"question": "내가 먹는 약과 같이 먹으면 안 되는 것 알려줘"}),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert len(client.all_messages) == 2
    assert "🧬 **약과 상호작용**" in outcome.result.answer
    assert "🍗 **그 외 상호작용**" in outcome.result.answer
    assert "메나테트레논" in outcome.result.answer
    assert "녹차·홍차·우롱차" in outcome.result.answer
    assert "확인하지 못했습니다" not in outcome.result.answer
    assert outcome.result.sources == result.sources
    assert outcome.observation.fallback_used is not repair_succeeds


@pytest.mark.parametrize(
    "answer",
    [
        "🧬 **약과 상호작용**\n\n- 메나테트레논은 와파린의 항응고 효과를 감소시킬 수 있습니다.",
        "🍗 **그 외 상호작용**\n\n- 현재 근거에서는 해당 조합을 확인하지 못했습니다.",
        "🔁 **질문 상호작용**\n\n**[마그네슘-아연]**\n\n- 해당 조합의 직접 근거를 확인하지 못했습니다.",
    ],
)
async def test_generator_does_not_require_absent_overview_categories(answer: str) -> None:
    client = FakeAnswerClient(response={"answer": answer, "section_types": ["INTERACTION"]})
    result = build_result().model_copy(update={"answer": answer, "route": MedicationChatRoute.INTERACTION})
    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request(), context=ActiveIntakeContext(user_id=1), result=result
    )
    assert len(client.all_messages) == 1
    assert outcome.observation.fallback_used is False
    assert outcome.result.answer.split() == answer.split()


async def test_generator_compacts_adverse_effect_list_and_keeps_official_stop_instruction() -> None:
    warning = "이 약 복용 후 발진이 나타나면 즉시 복용을 중단하십시오."
    long_answer = (
        "**타이레놀산500밀리그램(아세트아미노펜)**\n\n🚨 **이상반응**\n- "
        "쇽증상과 천식발작, 혈소판감소, 과립구감소, 용혈성빈혈, 메트헤모글로빈혈증, 혈소판기능저하, "
        "청색증, 과민증상, 구역, 구토, 식욕부진, 위장출혈 등이 발생하는 경우 " + warning
    )
    concise_answer = (
        "**타이레놀산500밀리그램(아세트아미노펜)**\n\n🚨 **이상반응**\n- "
        "쇽증상·천식발작·과민반응 등이 나타나면 복용을 중단하고 상담하세요.\n- " + warning
    )
    client = FakeAnswerClient(
        responses=[
            {"answer": long_answer, "section_types": ["CAUTION"]},
            {"answer": concise_answer, "section_types": ["CAUTION"]},
        ]
    )
    result = build_result().model_copy(
        update={
            "answer": long_answer,
            "official_warning_texts": [warning],
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(
        request=build_request().model_copy(update={"question": "타이레놀산 이상반응만 알려줘"}),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert len(client.all_messages) == 2
    assert warning in outcome.result.answer
    assert "메트헤모글로빈혈증" not in outcome.result.answer
    assert outcome.observation.status == MedicationAnswerRewriteStatus.REWRITTEN


async def test_generator_repairs_uncovered_section_in_public_knowledge_summary() -> None:
    """단일 성분 원문을 요약하다 섹션을 잘못 선언해도 원문으로 바로 돌아가지 않는다."""

    draft = (
        "**와파린**\n\n✉️ **안내사항**\n\n"
        "- 키워드 와파린약물동태학상호작용녹차홍차,,,,\n\n1.차\n\n"
        "녹차뿐만아니라홍차및우롱차에는비타민K가함유되어있다. "
        "비타민K는와파린의항응고효과를감소시킬수있다."
    )
    summary = "**와파린**\n\n✉️ **안내사항**\n\n- 비타민 K는 와파린의 항응고 효과를 줄일 수 있습니다."
    client = FakeAnswerClient(
        responses=[
            {"answer": summary, "section_types": ["CAUTION"]},
            {"answer": summary, "section_types": []},
        ]
    )
    result = build_result().model_copy(
        update={
            "answer": draft,
            "sources": [
                MedicationChatSource(
                    kind=MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
                    title="와파린과 생약 및 식품의 상호작용",
                )
            ],
            "evidence_coverage": MedicationEvidenceCoverage(requested_section_types=[], covered_section_types=[]),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(
        request=build_request().model_copy(update={"question": "와파린"}),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert outcome.result.answer == summary
    assert outcome.observation.status == MedicationAnswerRewriteStatus.REWRITTEN
    assert outcome.observation.fallback_used is False
    assert outcome.observation.declared_section_types == []
    assert len(client.all_messages) == 2
    assert "covered_section_types" in client.all_messages[-1][-1].content
    assert "5개" in client.all_messages[-1][-1].content
    assert outcome.result.sources == result.sources


async def test_generator_revalidates_repaired_section_without_allowing_new_dosage() -> None:
    client = FakeAnswerClient(
        responses=[
            {"answer": "⚠️ **주의사항**\n- 복용 시 주의가 필요합니다.", "section_types": ["CAUTION"]},
            {"answer": "✉️ **안내사항**\n- 하루 10정을 복용하세요.", "section_types": []},
        ]
    )
    result = build_result().model_copy(
        update={"evidence_coverage": MedicationEvidenceCoverage(requested_section_types=[], covered_section_types=[])}
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(request=build_request(), context=ActiveIntakeContext(user_id=1), result=result)

    assert len(client.all_messages) == 2
    assert outcome.result.answer == result.answer
    assert outcome.observation.fallback_reason == MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT


@pytest.mark.parametrize("day", ["일일", "하루", "1일"])
async def test_generator_accepts_dosage_rewrite_that_only_removes_thousands_separator(day) -> None:
    draft = "⚠️ **주의사항**\n- 아세트아미노펜으로 일일 최대용량(4,000mg)을 초과하여 복용하지 마십시오."
    rewritten = f"⚠️ **주의사항**\n- 아세트아미노펜은 {day} 최대용량 4000mg을 넘지 마세요."
    client = FakeAnswerClient(response={"answer": rewritten, "section_types": ["CAUTION"]})
    result = build_result().model_copy(
        update={
            "answer": draft,
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(request=build_request(), context=ActiveIntakeContext(user_id=1), result=result)

    assert outcome.result.answer == rewritten
    assert outcome.observation.status is MedicationAnswerRewriteStatus.REWRITTEN
    assert outcome.observation.fallback_used is False


@pytest.mark.parametrize("rewritten_subject", ["타이레놀정500밀리그램(아세트아미노펜)", "타이레놀정500mg"])
async def test_generator_accepts_product_heading_unit_spelling_equivalence(rewritten_subject: str) -> None:
    draft = "**타이레놀정500밀리그람(아세트아미노펜)**\n\n✅ **효능**\n- 감기로 인한 발열 및 통증에 사용합니다."
    rewritten = f"**{rewritten_subject}**\n\n✅ **효능**\n- 감기로 인한 발열과 통증에 쓰입니다."
    client = FakeAnswerClient(response={"answer": rewritten, "section_types": ["FUNCTION"]})
    result = build_result().model_copy(
        update={
            "answer": draft,
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.FUNCTION],
                covered_section_types=[KnowledgeSectionType.FUNCTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(request=build_request(), context=ActiveIntakeContext(user_id=1), result=result)

    assert outcome.result.answer == rewritten
    assert outcome.observation.status is MedicationAnswerRewriteStatus.REWRITTEN
    assert outcome.observation.fallback_used is False


@pytest.mark.parametrize(
    "strength_context",
    [
        "**타이레놀정500밀리그람**\n\n",
        "💊 **복약정보**\n- 타이레놀정500밀리그람\n\n---\n\n",
    ],
)
@pytest.mark.parametrize(
    "instruction", ["- 500mg 복용하세요.", "**500mg 복용하세요.**", "**타이레놀정500mg(500mg 복용하세요)**"]
)
def test_product_strength_does_not_authorize_new_dosing_instruction(strength_context: str, instruction: str) -> None:
    failure = OpenAIMedicationAnswerGenerator._grounding_failure_reason(
        draft_answer=f"{strength_context}✅ **효능**\n- 해열에 사용합니다.",
        generated_answer=f"{strength_context}✅ **효능**\n- 해열에 사용합니다.\n{instruction}",
    )
    assert failure is MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT


def test_new_instruction_inside_inventory_is_not_treated_as_registered_name() -> None:
    failure = OpenAIMedicationAnswerGenerator._grounding_failure_reason(
        draft_answer="💊 **복약정보**\n- 타이레놀정500밀리그람\n\n---\n\n✅ **효능**\n- 해열에 사용합니다.",
        generated_answer="💊 **복약정보**\n- 500mg 복용하세요.\n\n---\n\n✅ **효능**\n- 해열에 사용합니다.",
    )
    assert failure is MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT


def test_product_heading_strength_change_remains_unsupported() -> None:
    failure = OpenAIMedicationAnswerGenerator._grounding_failure_reason(
        draft_answer="**타이레놀정500밀리그람**\n\n✅ **효능**\n- 해열에 사용합니다.",
        generated_answer="**타이레놀정600mg**\n\n✅ **효능**\n- 해열에 사용합니다.",
    )
    assert failure is MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT


@pytest.mark.parametrize(
    ("draft_dosage", "rewritten_dosage"),
    [
        ("400μg", "400mcg"),
        ("400㎍", "400mcg"),
        ("400mcg", "400㎍"),
    ],
)
async def test_generator_accepts_microgram_unit_spelling_equivalence(
    draft_dosage: str,
    rewritten_dosage: str,
) -> None:
    client = FakeAnswerClient(
        response={"answer": f"⚠️ **주의사항**\n- 하루 {rewritten_dosage}을 넘지 마세요.", "section_types": ["CAUTION"]}
    )
    result = build_result().model_copy(
        update={
            "answer": f"⚠️ **주의사항**\n- 하루 {draft_dosage}을 넘지 마세요.",
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(request=build_request(), context=ActiveIntakeContext(user_id=1), result=result)

    assert outcome.observation.status is MedicationAnswerRewriteStatus.REWRITTEN
    assert outcome.observation.fallback_used is False


async def test_generator_still_rejects_new_numeric_dosage_after_normalization() -> None:
    client = FakeAnswerClient(
        response={"answer": "⚠️ **주의사항**\n- 하루 5000mg을 넘지 마세요.", "section_types": ["CAUTION"]}
    )
    result = build_result().model_copy(
        update={
            "answer": "⚠️ **주의사항**\n- 하루 4,000mg을 넘지 마세요.",
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(request=build_request(), context=ActiveIntakeContext(user_id=1), result=result)

    assert outcome.result.answer == result.answer
    assert outcome.observation.fallback_reason is MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT


async def test_generator_does_not_treat_decimal_point_as_thousands_separator() -> None:
    client = FakeAnswerClient(
        response={"answer": "⚠️ **주의사항**\n- 하루 4000mg을 넘지 마세요.", "section_types": ["CAUTION"]}
    )
    result = build_result().model_copy(
        update={
            "answer": "⚠️ **주의사항**\n- 하루 4.000mg을 넘지 마세요.",
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(request=build_request(), context=ActiveIntakeContext(user_id=1), result=result)

    assert outcome.result.answer == result.answer
    assert outcome.observation.fallback_reason is MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT


async def test_generator_keeps_official_warning_verbatim_when_rewrite_changes_the_condition() -> None:
    """공식 주의사항의 조건을 바꾼 중단 지시는 초안으로 되돌려 안전성 차단을 막는다."""

    warning = "이 약 복용 후 피부 발진 또는 과민반응의 징후가 나타나는 경우 즉시 복용을 중단하십시오."
    initial = build_result().model_copy(
        update={
            "answer": "⚠️ **주의사항**\n- " + warning,
            "official_warning_texts": [warning],
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(
            response={
                "answer": "⚠️ **주의사항**\n- 두통이 나타나면 이 약 복용을 중단하세요.",
                "section_types": ["CAUTION"],
            }
        ),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result.answer == initial.answer
    # 초안이 그대로 나갔으므로 지표도 재작성 성공이 아니라 초안 노출로 기록돼야 한다.
    assert outcome.observation.status is MedicationAnswerRewriteStatus.DRAFT_FALLBACK
    assert outcome.observation.fallback_reason is MedicationAnswerFallbackReason.OFFICIAL_WARNING_PRESERVED


@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_generator_uses_shared_repair_for_official_warning_failure(repair_succeeds: bool) -> None:
    warning = "이 약 복용 후 발진이 나타나면 즉시 복용을 중단하십시오."
    invalid = "⚠️ **주의사항**\n- 두통이 나타나면 이 약 복용을 중단하세요."
    repaired = "⚠️ **주의사항**\n- " + warning
    result = build_result().model_copy(
        update={
            "answer": repaired + "\n- " + "주변의 긴 부연 설명입니다. " * 20,
            "official_warning_texts": [warning],
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.CAUTION],
            ),
        }
    )
    client = FakeAnswerClient(
        responses=[
            {"answer": invalid, "section_types": ["CAUTION"]},
            {"answer": repaired if repair_succeeds else invalid, "section_types": ["CAUTION"]},
        ]
    )

    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request(), context=ActiveIntakeContext(user_id=1), result=result
    )

    assert len(client.all_messages) == 2
    assert warning in str(client.all_messages[-1])
    assert outcome.result.answer == (repaired if repair_succeeds else result.answer)
    assert outcome.observation.fallback_used is not repair_succeeds
    assert outcome.observation.fallback_reason == (
        None if repair_succeeds else MedicationAnswerFallbackReason.OFFICIAL_WARNING_PRESERVED
    )


async def test_generator_does_not_start_a_second_repair_after_format_repair_breaks_warning() -> None:
    warning = "이 약 복용 후 발진이 나타나면 즉시 복용을 중단하십시오."
    # 조건이 다른 생성문은 형식 보정 뒤에도 기존 validator로 거부한다.
    draft = "⚠️ **주의사항**\n- " + warning
    invalid = "⚠️ **주의사항**\n- 두통이 나타나면 이 약 복용을 중단하세요."
    client = FakeAnswerClient(
        responses=[
            {"answer": draft + "\n- " + "긴 설명입니다. " * 20, "section_types": ["CAUTION"]},
            {"answer": invalid, "section_types": ["CAUTION"]},
        ]
    )
    result = build_result().model_copy(update={"answer": draft, "official_warning_texts": [warning]})

    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request(), context=ActiveIntakeContext(user_id=1), result=result
    )

    assert len(client.all_messages) == 2
    assert outcome.result.answer == draft
    assert outcome.observation.fallback_reason is MedicationAnswerFallbackReason.OFFICIAL_WARNING_PRESERVED


def test_generator_restores_missing_subject_after_inventory_separator() -> None:
    draft = "**약 A**\n\n✅ **효능**\n- 근거에 있는 핵심 효능."
    generated = "💊 **복약정보**\n- 약 B\n\n---\n\n✅ **효능**\n- 근거에 있는 핵심 효능."

    answer = OpenAIMedicationAnswerGenerator._format_generated_answer(draft_answer=draft, generated_answer=generated)

    assert answer == "💊 **복약정보**\n- 약 B\n\n---\n\n**약 A**\n\n✅ **효능**\n- 근거에 있는 핵심 효능."


async def test_generator_restores_named_ingredient_heading_omitted_by_llm() -> None:
    client = FakeAnswerClient(
        response={
            "answer": "✅ **효능**\n- 수면의 질 개선에 도움을 줄 수 있습니다.\n\n⚠️ **주의사항**\n- 섭취 전 제품 안내를 확인하세요.",
            "section_types": ["FUNCTION", "CAUTION"],
        }
    )
    result = build_result().model_copy(
        update={
            "answer": (
                "**멜라토닌**\n\n"
                "✅ **효능**\n- 수면의 질 개선에 도움을 줄 수 있습니다.\n\n"
                "⚠️ **주의사항**\n- 섭취 전 제품 안내를 확인하세요."
            ),
            "route": MedicationChatRoute.SUPPLEMENT_GUIDE,
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.FUNCTION, KnowledgeSectionType.CAUTION],
                covered_section_types=[KnowledgeSectionType.FUNCTION, KnowledgeSectionType.CAUTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(
        request=MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="수면의 질 개선과 관련된 건강기능식품 기능 정보가 있나요?",
        ),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert outcome.result.answer.startswith("**멜라토닌**\n\n✅ **효능**")


async def test_generator_repairs_interaction_to_the_requested_pair_only() -> None:
    client = FakeAnswerClient(
        responses=[
            {
                "answer": (
                    "🔁 **질문 상호작용**\n\n**[와파린-비타민 K]**\n"
                    "- 녹차와 홍차와 캐모마일과 크랜베리 등 여러 식품의 상세 내용을 포함한 긴 원문입니다."
                ),
                "section_types": ["INTERACTION"],
            },
            {
                "answer": (
                    "🔁 **질문 상호작용**\n\n**[와파린-비타민 K]**\n"
                    "- 비타민 K는 와파린의 항응고 효과를 낮출 수 있습니다."
                ),
                "section_types": ["INTERACTION"],
            },
        ]
    )
    result = build_result().model_copy(
        update={
            "answer": "🔁 **질문 상호작용**\n\n**[와파린-비타민 K]**\n- 직접 근거를 확인했습니다.",
            "route": MedicationChatRoute.INTERACTION,
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.INTERACTION],
                covered_section_types=[KnowledgeSectionType.INTERACTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(
        request=MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="와파린과 비타민 K를 같이 먹어도 되나요?",
        ),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert "**[와파린-비타민 K]**" in outcome.result.answer
    assert "녹차" not in outcome.result.answer
    assert len(client.all_messages) == 2


def test_adverse_detail_does_not_turn_causality_rubric_into_a_case_assessment() -> None:
    rubric = [
        "WHO-UMC 인과성 평가 기준 Causality term Assessment criteria",
        "확실함 Certain 상당히 확실함 Probable/Likely 가능함 Possible",
    ]
    assert OpenAIMedicationAnswerGenerator._compact_adverse_detail(rubric) is None


async def test_generator_compacts_an_unrepaired_adverse_case_report() -> None:
    raw_report = (
        "🩻 **부작용 보고서**\n\n"
        "**이상사례**\n\n"
        "- 2) 이상사례: 현기증 (어지러움)\n\n"
        "**상세 사항**\n\n"
        "- 상세 사항 → WHO-UMC 평가기준 '상당히 확실함'입니다. "
        "약물투여와 이상사례 발생간에 시간적 연관성이 있고 질병이나 다른 약물에 의한 것으로 보이지 않으며 "
        "약물 복용을 중단했을 때 어지러움증이 호전되는 임상적 변화가 있었습니다. "
        "참고로 탐스로신이 독사조신보다 효과적일 수 있다는 비교 연구도 있습니다."
    )
    client = FakeAnswerClient(
        responses=[
            {
                "answer": raw_report,
                "section_types": ["ADVERSE_EVENT", "CASE_SUMMARY", "ASSESSMENT"],
            },
            {
                "answer": raw_report,
                "section_types": ["ADVERSE_EVENT", "CASE_SUMMARY", "ASSESSMENT"],
            },
        ]
    )
    result = build_result().model_copy(
        update={
            "answer": raw_report,
            "route": MedicationChatRoute.GENERAL_GUIDANCE,
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[],
                covered_section_types=[],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(
        request=MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="독사조신 복용 후 심한 어지러움이 보고된 사례가 있나요?",
        ),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert outcome.result.answer.startswith("🩻 **부작용 리포트**")
    assert "**추가설명**" in outcome.result.answer
    assert "현기증" in outcome.result.answer
    assert "WHO-UMC 평가에서 상당히 확실함으로 분류됨." in outcome.result.answer
    assert "탐스로신" not in outcome.result.answer
    assert "비교 연구" not in outcome.result.answer
    assert all(
        len(line.removeprefix("- ").split()) <= 10
        for line in outcome.result.answer.splitlines()
        if line.startswith("- ")
    )


async def test_generator_compacts_adverse_case_report_when_evidence_coverage_falls_back() -> None:
    raw_report = (
        "🩻 **부작용 보고서**\n\n"
        "**이상사례**\n\n"
        "- 2) 이상사례: 현기증 (어지러움)\n\n"
        "**상세 사항**\n\n"
        "- 상세 사항 → WHO-UMC 평가기준 '상당히 확실함'입니다. "
        "약물투여와 이상사례 발생간에 시간적 연관성이 있습니다."
    )
    client = FakeAnswerClient(
        response={
            "answer": "🩻 **부작용 보고서**\n\n**이상사례**\n- 현기증이 보고됨.",
            "section_types": ["ADVERSE_EVENT", "ASSESSMENT"],
        }
    )
    result = build_result().model_copy(
        update={
            "answer": raw_report,
            "route": MedicationChatRoute.GENERAL_GUIDANCE,
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[],
                covered_section_types=[],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)

    outcome = await generator.generate(
        request=MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="독사조신 복용 후 심한 어지러움이 보고된 사례가 있나요?",
        ),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert outcome.observation.status == MedicationAnswerRewriteStatus.DRAFT_FALLBACK
    assert outcome.result.answer.startswith("🩻 **부작용 리포트**")
    assert "**추가설명**" in outcome.result.answer
    assert "현기증이 보고됨." in outcome.result.answer
    assert "WHO-UMC 평가에서 상당히 확실함으로 분류됨." in outcome.result.answer
    assert "시간적 연관성" not in outcome.result.answer


def test_adverse_report_headers_normalize_without_changing_other_sections() -> None:
    generator = OpenAIMedicationAnswerGenerator
    legacy = "🩻 **부작용 보고서**\n\n**이상사례**\n- 현기증\n\n**상세 사항**\n- 경과를 검토했습니다."
    expected = legacy.replace("부작용 보고서", "부작용 리포트").replace("상세 사항", "추가설명")
    assert generator._to_limited_markdown(legacy) == expected
    assert generator._to_limited_markdown(expected) == expected
    assert generator._is_adverse_case_report(legacy)
    assert generator._is_adverse_case_report(expected)
    assert generator._adverse_report_lines(expected) == (["현기증"], ["경과를 검토했습니다."])
    assert generator._to_limited_markdown("**상세 사항**\n- 다른 정보") == "**상세 사항**\n- 다른 정보"


async def test_generator_uses_accurate_model_for_interaction_answer_when_enabled() -> None:
    fast_client = FakeAnswerClient(error=AssertionError("빠른 모델을 호출하면 안 됩니다."))
    accurate_client = FakeAnswerClient(
        response={
            "answer": "🔁 **질문 상호작용**\n\n**[타이레놀-비타민 D]**\n- 직접 근거를 확인합니다.",
            "section_types": ["INTERACTION"],
        }
    )
    result = build_result().model_copy(
        update={
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.INTERACTION],
                covered_section_types=[KnowledgeSectionType.INTERACTION],
            )
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=fast_client,
        accurate_model="gpt-4o-2024-11-20",
        accurate_client=accurate_client,
        high_accuracy_routing_enabled=True,
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert fast_client.messages is None
    assert accurate_client.messages is not None
    assert outcome.result.model_name == "gpt-4o-2024-11-20"


async def test_generator_restores_required_question_interaction_pair_labels() -> None:
    client = FakeAnswerClient(
        response={
            "answer": (
                "🔁 **질문 상호작용**\n- 펙소페나딘은 과일 주스와 함께 복용하면 흡수에 영향을 받을 수 있습니다."
            ),
            "section_types": ["INTERACTION"],
        }
    )
    result = build_result().model_copy(
        update={
            "answer": (
                "🔁 **질문 상호작용**\n\n"
                "**[펙소페나딘-자몽주스]**\n"
                "- 자몽주스와 함께 복용하면 흡수에 영향을 받을 수 있습니다.\n\n"
                "**[펙소페나딘-사과주스]**\n"
                "- 사과주스와 함께 복용하면 흡수에 영향을 받을 수 있습니다."
            ),
            "route": MedicationChatRoute.INTERACTION,
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.INTERACTION],
                covered_section_types=[KnowledgeSectionType.INTERACTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=client,
    )

    outcome = await generator.generate(
        request=MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="펙소페나딘과 자몽주스, 사과주스를 같이 먹어도 돼?",
        ),
        context=ActiveIntakeContext(user_id=1),
        result=result,
    )

    assert outcome.observation.status == MedicationAnswerRewriteStatus.REWRITTEN
    assert "**[펙소페나딘-자몽주스]**" in outcome.result.answer
    assert "**[펙소페나딘-사과주스]**" in outcome.result.answer


def build_grounded_pair_summary_result() -> MedicationChatResult:
    return build_result().model_copy(
        update={
            "answer": (
                "💊 **복약정보**\n- 와파린\n\n---\n\n"
                "🔁 **질문 상호작용**\n\n**[와파린-비타민 K]**\n"
                "- 키워드와목차를포함한OCR원문. 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다."
            ),
            "route": MedicationChatRoute.INTERACTION,
            "search_observation": MedicationSearchExecutionObservation.model_validate(
                {
                    "query_plan": {
                        "original_query": "와파린과 비타민 K 상호작용",
                        "expanded_query": "와파린과 비타민 K 상호작용",
                        "interaction_pairs": [
                            {
                                "left_name": "와파린",
                                "right_name": "비타민 K",
                                "pair_type": "DRUG_SUPPLEMENT",
                                "pair_key": "a" * 64,
                            }
                        ],
                        "interaction_pair_keys": ["a" * 64],
                    },
                    "query_plan_hash": "b" * 64,
                    "execution_plan_hash": "c" * 64,
                }
            ),
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.INTERACTION],
                covered_section_types=[KnowledgeSectionType.INTERACTION],
                verified_interaction_pair_keys=["a" * 64],
            ),
            "evidence_reasoning": EvidenceReasoningOutput.model_validate(
                {
                    "reasoning_status": "SUPPORTED",
                    "interaction_decision": "INTERACTION_CONFIRMED",
                    "claims": [
                        {
                            "section_type": "INTERACTION",
                            "pair_key": "a" * 64,
                            "statement": "비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다.",
                            "evidence_ids": ["chunk:source-a"],
                        }
                    ],
                }
            ),
        }
    )


async def test_generator_restores_pair_heading_from_exact_grounded_overview_without_raw_ocr() -> None:
    client = FakeAnswerClient(
        response={
            "answer": (
                "💊 **복약정보**\n- 와파린\n\n---\n\n🧬 **약과 상호작용**\n"
                "- 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다."
            ),
            "section_types": ["INTERACTION"],
        }
    )
    result = build_grounded_pair_summary_result()
    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request(), context=ActiveIntakeContext(user_id=1), result=result
    )

    assert "OCR원문" not in outcome.result.answer
    assert outcome.result.answer.count("비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다.") == 1
    assert "**[와파린-비타민 K]**\n- 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다." in outcome.result.answer
    assert outcome.result.answer.startswith("💊 **복약정보**\n- 와파린\n\n---")
    assert outcome.observation.status is MedicationAnswerRewriteStatus.REWRITTEN
    assert outcome.result.evidence_reasoning == result.evidence_reasoning
    assert len(client.all_messages) == 1


@pytest.mark.parametrize("mismatch", ["claim_pair", "unverified_pair", "missing_plan", "different_statement"])
async def test_generator_does_not_relabel_unbound_overview_claim(mismatch: str) -> None:
    result = build_grounded_pair_summary_result()
    statement = "비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다."
    if mismatch == "claim_pair":
        claim = result.evidence_reasoning.claims[0].model_copy(update={"pair_key": "d" * 64})
        result = result.model_copy(
            update={"evidence_reasoning": result.evidence_reasoning.model_copy(update={"claims": [claim]})}
        )
    elif mismatch == "unverified_pair":
        result = result.model_copy(
            update={
                "evidence_coverage": result.evidence_coverage.model_copy(update={"verified_interaction_pair_keys": []})
            }
        )
    elif mismatch == "missing_plan":
        result = result.model_copy(update={"search_observation": None})
    else:
        statement = "비타민 K는 와파린의 항응고 효과를 증가시킬 수 있습니다."
    client = FakeAnswerClient(
        response={"answer": "🧬 **약과 상호작용**\n- " + statement, "section_types": ["INTERACTION"]}
    )

    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request(), context=ActiveIntakeContext(user_id=1), result=result
    )

    question_section = outcome.result.answer.split("🔁 **질문 상호작용**", 1)[1]
    assert [line for line in question_section.splitlines() if line.strip()] == [
        "**[와파린-비타민 K]**",
        "- 키워드와목차를포함한OCR원문. 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다.",
    ]


def test_generator_restores_only_missing_pair_without_overwriting_another_summary() -> None:
    draft = (
        "🔁 **질문 상호작용**\n\n**[약 A-성분 B]**\n- 첫 조합의 긴 원문 설명.\n\n"
        "**[약 A-성분 C]**\n- 두 번째 조합은 직접 근거를 확인하지 못했습니다."
    )
    generated = "🔁 **질문 상호작용**\n\n**[약 A-성분 B]**\n- 첫 조합의 짧은 요약."

    answer = OpenAIMedicationAnswerGenerator._format_generated_answer(draft_answer=draft, generated_answer=generated)

    first, second = answer.split("**[약 A-성분 C]**")
    assert "첫 조합의 짧은 요약." in first
    assert "긴 원문" not in answer
    assert "첫 조합" not in second
    assert "두 번째 조합은 직접 근거를 확인하지 못했습니다." in second


async def test_generator_reuses_grounded_summary_only_for_its_pair_in_multi_pair_draft() -> None:
    result = build_grounded_pair_summary_result()
    result = result.model_copy(
        update={"answer": result.answer + "\n\n**[와파린-다른 성분]**\n- 다른 조합의 직접 근거를 확인하지 못했습니다."}
    )
    client = FakeAnswerClient(
        response={
            "answer": "🧬 **약과 상호작용**\n- 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다.",
            "section_types": ["INTERACTION"],
        }
    )

    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request(), context=ActiveIntakeContext(user_id=1), result=result
    )

    first, second = outcome.result.answer.split("**[와파린-다른 성분]**")
    assert "**[와파린-비타민 K]**\n- 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다." in first
    assert "OCR원문" not in first
    assert second.strip() == "- 다른 조합의 직접 근거를 확인하지 못했습니다."


@pytest.mark.parametrize("qualifier", ["scope_note", "continuation", "other_pair_heading"])
async def test_generator_does_not_move_scoped_or_other_pair_overview_text(qualifier: str) -> None:
    result = build_grounded_pair_summary_result()
    statement = "비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다."
    overview = "🧬 **약과 상호작용**\n- " + statement
    if qualifier == "scope_note":
        claim = result.evidence_reasoning.claims[0].model_copy(update={"scope_note": "특정 연구 조건에 한함"})
        result = result.model_copy(
            update={"evidence_reasoning": result.evidence_reasoning.model_copy(update={"claims": [claim]})}
        )
    elif qualifier == "continuation":
        overview += "\n  특정 연구 조건에 한함."
    else:
        overview = "🧬 **약과 상호작용**\n**[다른 약-다른 성분]**\n- " + statement
    client = FakeAnswerClient(response={"answer": overview, "section_types": ["INTERACTION"]})

    outcome = await OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client).generate(
        request=build_request(), context=ActiveIntakeContext(user_id=1), result=result
    )

    question_section = outcome.result.answer.split("🔁 **질문 상호작용**", 1)[1]
    assert [line for line in question_section.splitlines() if line.strip()] == [
        "**[와파린-비타민 K]**",
        "- 키워드와목차를포함한OCR원문. 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다.",
    ]


def test_generator_keeps_each_pair_fact_under_its_own_heading() -> None:
    answer = "🔁 **질문 상호작용**\n\n**[약 A-성분 B]**\n- 첫 조합의 사실.\n\n**[약 A-성분 C]**\n- 두 번째 조합의 사실."

    formatted = OpenAIMedicationAnswerGenerator._to_limited_markdown(answer)

    first, second = formatted.split("**[약 A-성분 C]**")
    assert "첫 조합의 사실." in first
    assert "첫 조합의 사실." not in second
    assert "두 번째 조합의 사실." in second


def test_generator_preserves_warning_and_contraindication_section_markdown() -> None:
    answer = OpenAIMedicationAnswerGenerator._to_limited_markdown(
        "⚠️ **주의사항**\n- 정기적 음주자는 복용 전 확인합니다."
        "\n\n🚫 **복용하면 안 되는 경우**\n- 과민증이 있으면 복용하지 않습니다."
    )

    assert answer.startswith("⚠️ **주의사항**")
    assert "🚫 **복용하면 안 되는 경우**" in answer


def test_generator_preserves_adverse_reaction_section_markdown() -> None:
    answer = OpenAIMedicationAnswerGenerator._to_limited_markdown(
        "🚨 **이상반응**\n- 발진이나 호흡 곤란이 나타나면 즉시 진료를 받으세요."
    )

    assert answer.startswith("🚨 **이상반응**")


def test_generator_preserves_standalone_bold_product_name() -> None:
    answer = OpenAIMedicationAnswerGenerator._to_limited_markdown(
        "**타이레놀산(아세트아미노펜)**\n\n✅ **효능**\n- 감기로 인한 발열 및 통증에 사용합니다."
    )

    assert answer.startswith("**타이레놀산(아세트아미노펜)**")


def test_generator_restores_magnesium_formulation_cautions_when_rewrite_merges_them() -> None:
    draft_answer = (
        "**마그네슘**\n\n"
        "⚠️ **주의사항**\n\n"
        "**수산화마그네슘**\n"
        "- 신장 질환이 있으면 복용 전 상담합니다.\n\n"
        "**산화마그네슘**\n"
        "- 묽은 변이 나타날 수 있습니다."
    )
    generated_answer = "**마그네슘**\n\n⚠️ **주의사항**\n- 복용 전 주의사항을 확인합니다."

    answer = OpenAIMedicationAnswerGenerator._format_generated_answer(
        draft_answer=draft_answer,
        generated_answer=generated_answer,
    )

    assert "**수산화마그네슘**" in answer
    assert "신장 질환이 있으면 복용 전 상담합니다." in answer
    assert "**산화마그네슘**" in answer
    assert "묽은 변이 나타날 수 있습니다." in answer


def test_generator_preserves_active_intake_section_markdown() -> None:
    answer = OpenAIMedicationAnswerGenerator._to_limited_markdown(
        "💊 **복약정보**\n- 가상 약 A · 1정\n\n💪🏻 **영양제 정보**\n- 가상 영양제 B · 1캡슐"
    )

    assert answer.startswith("💊 **복약정보**")
    assert "💪🏻 **영양제 정보**" in answer


def test_generator_preserves_question_interaction_pair_and_intake_divider() -> None:
    answer = OpenAIMedicationAnswerGenerator._to_limited_markdown(
        "💊 **복약정보**\n- 세레콕시브캡슐200mg\n\n---\n\n"
        "🔁 **질문 상호작용**\n\n**[타이레놀-마그네슘]**\n"
        "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 못했습니다."
    )

    assert "---" in answer
    assert "🔁 **질문 상호작용**" in answer
    assert "**[타이레놀-마그네슘]**" in answer
    assert "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 못했습니다." in answer


def test_generator_keeps_combined_food_interaction_heading_at_top_level() -> None:
    draft_answer = (
        "**와파린**\n\n"
        "🔁 **약물 상호작용**\n\n"
        "**주의가 필요한 조합**\n"
        "- 메나테트레논 ↔ 와파린: 와파린의 항응고 효과가 감소할 수 있습니다.\n\n"
        "🔁 **음식 상호작용**\n\n"
        "**주의가 필요한 조합**\n"
        "- 녹차, 홍차, 우롱차: 비타민 K 함유로 와파린의 항응고 효과를 감소시킬 수 있습니다."
    )
    generated_answer = (
        "**와파린**\n\n"
        "🔁 **약물 상호작용**\n\n"
        "**주의가 필요한 조합**\n"
        "- 메나테트레논 ↔ 와파린: 와파린의 항응고 효과가 감소할 수 있습니다.\n"
        "  🔁 **음식 상호작용** **주의가 필요한 조합**\n"
        "- 녹차, 홍차, 우롱차: 비타민 K 함유로 와파린의 항응고 효과를 감소시킬 수 있습니다."
    )

    answer = OpenAIMedicationAnswerGenerator._format_generated_answer(
        draft_answer=draft_answer,
        generated_answer=generated_answer,
    )

    lines = answer.splitlines()
    food_heading_index = lines.index("🔁 **음식 상호작용** **주의가 필요한 조합**")
    # 목록 바로 다음 줄이면 마크다운이 그 항목의 연속으로 읽어 소제목이 들여쓰기된다.
    assert lines[food_heading_index - 1] == ""
    assert lines[food_heading_index - 2].startswith("- 메나테트레논")
    food_bullets = [line for line in lines[food_heading_index + 1 :] if line.strip()]
    assert food_bullets[0].startswith("- 녹차, 홍차, 우롱차:")


async def test_generator_skips_llm_when_no_grounded_sources() -> None:
    client = FakeAnswerClient(error=AssertionError("호출하면 안 됩니다."))
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=client,
    )
    initial = build_result().model_copy(update={"sources": []})

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result == initial
    assert outcome.observation.status == MedicationAnswerRewriteStatus.SKIPPED
    assert outcome.observation.fallback_reason == MedicationAnswerFallbackReason.NO_GROUNDED_SOURCES
    assert outcome.observation.generated_answer_hash is None


async def test_generator_uses_llm_for_low_risk_general_supplement_guidance_without_rag_source() -> None:
    client = FakeAnswerClient(
        response={
            "answer": (
                "✅ **함께 섭취 시 참고사항**\n\n"
                "- 마그네슘과 아연은 일반적으로 함께 섭취되는 영양성분입니다.\n"
                "- 제품별 총 섭취량과 속 불편함 여부를 확인해 주세요."
            ),
            "section_types": [],
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=client,
    )
    initial = build_result().model_copy(
        update={
            "route": MedicationChatRoute.SUPPLEMENT_GUIDE,
            "answer": "마그네슘과 아연 병용에 대한 직접 검색 근거는 확인되지 않았습니다.",
            "sources": [],
            "safety_reason_codes": ["GENERAL_SUPPLEMENT_GUIDANCE"],
            "risk_decision": MedicationChatRiskDecision(
                domain=MedicationChatAnswerDomain.SUPPLEMENT,
                scope=MedicationChatRiskScope.EVIDENCE_WITH_GENERAL_GUIDANCE,
            ),
        }
    )

    outcome = await generator.generate(
        request=MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="마그네슘과 아연을 같이 먹어도 돼?",
        ),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.observation.status == MedicationAnswerRewriteStatus.REWRITTEN
    assert "함께 섭취 시 참고사항" in outcome.result.answer
    assert client.messages is not None


async def test_generator_does_not_call_llm_for_evidence_gap_notice() -> None:
    """근거 부재 안내는 이미 최종 형식이며 보탤 사실이 없다.

    재작성을 맡기면 조회하지 못한 내용을 채워 넣을 자리만 생긴다.
    """

    client = FakeAnswerClient(error=AssertionError("호출하면 안 됩니다."))
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)
    draft = (
        "✉️ **안내사항**\n\n- 마그네슘 ↔ 아연 관련 자료를 찾지 못했습니다.\n\n"
        "📭 **공식 확인 경로**\n\n- 의약품은 의약품안전나라, 건강기능식품은 식품안전나라에서 확인할 수 있습니다."
    )
    initial = build_result().model_copy(
        update={
            "route": MedicationChatRoute.RESTRICTED,
            "answer": draft,
            "sources": [],
            "safety_reason_codes": [MedicationChatReasonCode.IN_SCOPE_NO_EVIDENCE.value],
        }
    )

    outcome = await generator.generate(
        request=MedicationChatRequest(
            request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
            user_id=1,
            question="마그네슘과 아연을 같이 먹어도 돼?",
        ),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert client.messages is None
    assert outcome.observation.status == MedicationAnswerRewriteStatus.SKIPPED
    assert outcome.observation.fallback_reason == MedicationAnswerFallbackReason.EVIDENCE_GAP_NOTICE
    assert outcome.result.answer == draft


async def test_generator_skips_llm_when_only_registered_intake_sources_exist() -> None:
    client = FakeAnswerClient(error=AssertionError("호출하면 안 됩니다."))
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=client,
    )
    initial = build_result().model_copy(
        update={
            "route": MedicationChatRoute.INTERACTION,
            "answer": (
                "복약정보\n- 와파린\n\n"
                "영양제 정보\n- 비타민 K · 1정\n\n"
                "확인된 상호작용\n"
                "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 못했습니다."
            ),
            "sources": [
                MedicationChatSource(
                    kind=MedicationChatSourceKind.PATIENT_MEDICATION,
                    title="사용자 확정 복약정보 · 와파린",
                    medication_id=1,
                    care_episode_id=1,
                ),
                MedicationChatSource(
                    kind=MedicationChatSourceKind.PATIENT_SUPPLEMENT,
                    title="사용자 복용 영양제 · 비타민 K",
                    user_supplement_id=1,
                ),
            ],
        }
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result == initial
    assert outcome.observation.status == MedicationAnswerRewriteStatus.SKIPPED
    assert outcome.observation.fallback_reason is not None
    assert outcome.observation.fallback_reason.value == "PATIENT_CONTEXT_ONLY"
    assert outcome.observation.generated_answer_hash is None


async def test_generator_wraps_client_failure() -> None:
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(error=RuntimeError("openai down")),
    )

    with pytest.raises(ChatAnswerGenerationError) as exc_info:
        await generator.generate(
            request=build_request(),
            context=ActiveIntakeContext(user_id=1),
            result=build_result(),
        )
    assert exc_info.value.reason_code == MedicationAnswerFallbackReason.CLIENT_ERROR


async def test_generator_keeps_only_limited_markdown_section_format() -> None:
    grounded_result = build_result().model_copy(
        update={
            "answer": ("일반 제품 안내\n- 안내된 사용법을 따릅니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다.")
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(
            response={
                "answer": (
                    "# 제품 안내\n"
                    "✅ **사용법**\n"
                    "* 안내된 사용법을 따릅니다.\n\n"
                    "이 안내는 의료진의 진료를 대체하지 않습니다."
                )
            }
        ),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=grounded_result,
    )

    assert "#" not in outcome.result.answer
    assert "✅ **사용법**" in outcome.result.answer
    assert "* 안내된 사용법을 따릅니다." in outcome.result.answer


async def test_generator_formats_interaction_prose_as_dash_bullet_list() -> None:
    initial = build_result().model_copy(
        update={
            "route": MedicationChatRoute.INTERACTION,
            "answer": "철분과 아연의 상호작용 연구 근거입니다.",
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.INTERACTION],
                covered_section_types=[KnowledgeSectionType.INTERACTION],
            ),
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(
            response={
                "answer": (
                    "✅ **상호작용**\n"
                    "수용액 형태에서는 철분이 아연 흡수를 낮출 수 있습니다. "
                    "일반 식사나 유아용 조제분유에서는 같은 영향이 확인되지 않았습니다. "
                    "아연 요구량이 높은 임신·수유부, 청소년, 유아는 더 주의가 필요합니다."
                ),
                "section_types": ["INTERACTION"],
            }
        ),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result.answer == (
        "✅ **상호작용**\n\n"
        "- 수용액 형태에서는 철분이 아연 흡수를 낮출 수 있습니다.\n"
        "- 일반 식사나 유아용 조제분유에서는 같은 영향이 확인되지 않았습니다.\n"
        "- 아연 요구량이 높은 임신·수유부, 청소년, 유아는 더 주의가 필요합니다."
    )


async def test_generator_falls_back_to_safe_draft_when_rewrite_adds_claims() -> None:
    initial = build_result()
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(
            response={"answer": ("이 약은 하루 10정을 먹어도 안전합니다. 이 안내는 의료진의 진료를 대체하지 않습니다.")}
        ),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result.answer == initial.answer
    assert outcome.result.safety_status == SafetyStatus.SAFE
    assert outcome.result.safety_reason_codes == []
    assert outcome.result.model_name == "gpt-4o-mini"
    assert outcome.observation.status == MedicationAnswerRewriteStatus.DRAFT_FALLBACK
    assert outcome.observation.fallback_used is True
    assert outcome.observation.fallback_reason == MedicationAnswerFallbackReason.UNSUPPORTED_SAFETY_ASSERTION


async def test_generator_falls_back_when_rewrite_adds_uncovered_section() -> None:
    initial = build_result().model_copy(
        update={
            "evidence_coverage": MedicationEvidenceCoverage(
                requested_section_types=[KnowledgeSectionType.FUNCTION],
                covered_section_types=[KnowledgeSectionType.FUNCTION],
            )
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(
            response={
                "answer": (
                    "효능: 통증을 완화합니다.\n"
                    "주의사항: 졸릴 수 있습니다.\n\n"
                    "이 안내는 의료진의 진료를 대체하지 않습니다."
                ),
                "section_types": ["FUNCTION", "CAUTION"],
            }
        ),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result.answer == initial.answer
    assert outcome.observation.status == MedicationAnswerRewriteStatus.DRAFT_FALLBACK
    assert outcome.observation.fallback_reason == (MedicationAnswerFallbackReason.UNSUPPORTED_EVIDENCE_SECTION)
    assert outcome.observation.declared_section_types == [
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.CAUTION,
    ]


async def test_generator_reports_dosage_fallback_reason() -> None:
    initial = build_result()
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(response={"answer": "이 약은 하루 10정을 복용하세요. 의료진과 상담하세요."}),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result.answer == initial.answer
    assert outcome.observation.fallback_reason == (MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT)


async def test_generator_skips_llm_for_clarification_route() -> None:
    client = FakeAnswerClient(error=AssertionError("호출하면 안 됩니다."))
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)
    initial = build_result().model_copy(update={"route": MedicationChatRoute.CLARIFICATION})

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result == initial
    assert outcome.observation.fallback_reason == (MedicationAnswerFallbackReason.CLARIFICATION_REQUIRED)
