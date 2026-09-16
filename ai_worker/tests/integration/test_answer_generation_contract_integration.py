"""Chain 4(answer_generation)가 실제 모델에서 답변 계약을 지키는지 확인한다.

단위 테스트는 초안 조립까지만 검증하므로, 초안을 실제로 어떻게 다시 쓰는지는
실모델 호출로만 확인할 수 있다. 기본은 skip이며 개발 중 판단용으로 실행한다.
"""

from datetime import date

import pytest
from langchain_openai import ChatOpenAI

from ai_worker.core.config import Config
from ai_worker.llm.chat_model_policy import ChatModelPolicy, ChatModelStage
from ai_worker.llm.prompts.medication_chat_prompt import build_medication_chat_messages
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
    MedicationAnswerPayload,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationEvidenceCoverage,
)

settings = Config()

pytestmark = pytest.mark.skipif(
    not (settings.RUN_OPENAI_INTEGRATION_TESTS and settings.OPENAI_API_KEY is not None),
    reason="실제 OpenAI 답변 생성 테스트는 RUN_OPENAI_INTEGRATION_TESTS=1과 OPENAI_API_KEY가 필요합니다.",
)

REQUEST_ID = "6925e6ec-259c-4a96-8e69-6d5e8a626f1e"

CAUTION = KnowledgeSectionType.CAUTION
DAILY_INTAKE = KnowledgeSectionType.DAILY_INTAKE
INTERACTION = KnowledgeSectionType.INTERACTION

CASES = [
    (
        "요청하지 않은 섹션은 본문에서 제외한다",
        "타이레놀 주의사항 알려줘",
        MedicationChatRoute.MEDICATION_GUIDE,
        [CAUTION],
        [CAUTION],
        (
            "**타이레놀정500밀리그램**\n\n"
            "✅ **효능**\n- 감기로 인한 발열과 통증 완화에 사용합니다.\n\n"
            "⚠️ **주의사항**\n- 음주 중에는 복용하지 마세요."
        ),
        ["주의사항"],
        ["효능", "발열과 통증 완화"],
    ),
    (
        "초안의 임시 제목과 검색 원문을 그대로 내보내지 않는다",
        "와파린에 대해 알려줘",
        MedicationChatRoute.MEDICATION_GUIDE,
        [],
        [],
        (
            "**와파린**\n\n"
            "공공자료 추가 설명\n"
            "- 와파린약물동태학상호작용녹차홍차캐모마일,,,,\n"
            "- 녹차홍차우롱차의비타민K는와파린의항응고효과를감소시킬수있다."
        ),
        ["비타민"],
        ["공공자료 추가 설명", "와파린약물동태학상호작용"],
    ),
    (
        "근거를 찾지 못한 항목을 침묵으로 생략하지 않는다",
        "타이레놀 복용법과 주의사항 알려줘",
        MedicationChatRoute.MEDICATION_GUIDE,
        [DAILY_INTAKE, CAUTION],
        [CAUTION],
        (
            "**타이레놀정500밀리그램**\n\n"
            "⚠️ **주의사항**\n- 음주 중에는 복용하지 마세요.\n\n"
            "근거를 확인하지 못한 항목\n- 복용법: 현재 근거에서 확인하지 못했습니다."
        ),
        ["확인"],
        [],
    ),
    (
        "등록 복약정보와 영양제 목록은 범위 제한과 무관하게 보존한다",
        "내가 먹는 약과 같이 먹으면 안 되는 것 알려줘",
        MedicationChatRoute.INTERACTION,
        [INTERACTION],
        [INTERACTION],
        (
            "💊 **복약정보**\n- 와파린\n\n"
            "💪🏻 **영양제 정보**\n- 비타민 D\n\n---\n\n"
            "🧬 **약과 상호작용**\n- 메나테트레논은 와파린의 항응고 효과를 감소시킬 수 있습니다."
        ),
        ["와파린", "비타민 D", "메나테트레논"],
        [],
    ),
    (
        "지정 조합 질문은 pair별 제목 형식을 유지한다",
        "타이레놀이랑 마그네슘 같이 먹어도 돼?",
        MedicationChatRoute.INTERACTION,
        [INTERACTION],
        [INTERACTION],
        "🔁 **질문 상호작용**\n\n**[타이레놀-마그네슘]**\n- 마그네슘은 타이레놀의 흡수를 늦출 수 있습니다.",
        ["타이레놀-마그네슘", "질문 상호작용"],
        ["약과 상호작용"],
    ),
    (
        "대상 탐색 질문은 유형별 섹션 형식을 유지한다",
        "와파린과 같이 먹으면 안 되는 것 알려줘",
        MedicationChatRoute.INTERACTION,
        [INTERACTION],
        [INTERACTION],
        (
            "🧬 **약과 상호작용**\n\n- 메나테트레논은 와파린의 항응고 효과를 감소시킬 수 있습니다.\n\n"
            "🍗 **그 외 상호작용**\n\n- 녹차·홍차·우롱차의 비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다."
        ),
        ["약과 상호작용", "그 외 상호작용", "메나테트레논"],
        ["질문 상호작용"],
    ),
]


async def test_answer_generation_keeps_answer_contract() -> None:
    # OpenAI 비동기 클라이언트는 생성된 이벤트 루프에 묶이므로 케이스를 한 테스트에서 공유한다.
    policy = ChatModelPolicy(
        fast_model=settings.OPENAI_FAST_CHAT_MODEL,
        accurate_model=settings.OPENAI_ACCURATE_CHAT_MODEL,
        high_accuracy_routing_enabled=settings.OPENAI_HIGH_ACCURACY_ROUTING_ENABLED,
    )
    context = ActiveIntakeContext(
        user_id=1,
        medications=[ActiveMedication(name="와파린", medication_id=1, care_episode_id=1)],
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=1,
                name="비타민 D",
                dose_amount="1",
                dose_unit="정",
                start_date=date(2026, 1, 1),
            )
        ],
    )

    violations: list[str] = []
    for name, question, route, requested, covered, draft, must_contain, must_not_contain in CASES:
        client = ChatOpenAI(
            model=policy.model_for(ChatModelStage.ANSWER_GENERATION, requested_section_types=requested),
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=0,
        ).with_structured_output(MedicationAnswerPayload, method="json_schema", strict=True)
        result = MedicationChatResult(
            request_id=REQUEST_ID,
            answer=draft,
            route=route,
            safety_status=SafetyStatus.SAFE,
            prompt_version="draft-v1",
            schema_version="medication-chat-result-v1",
            evidence_coverage=MedicationEvidenceCoverage(
                requested_section_types=requested,
                covered_section_types=covered,
            ),
        )
        payload = await client.ainvoke(
            build_medication_chat_messages(
                request=MedicationChatRequest(request_id=REQUEST_ID, user_id=1, question=question),
                context=context,
                result=result,
            )
        )
        missing = [token for token in must_contain if token not in payload.answer]
        leaked = [token for token in must_not_contain if token in payload.answer]
        if missing or leaked:
            violations.append(f"{name}: 누락={missing} 노출={leaked}\n    출력: {payload.answer!r}")

    assert not violations, "답변 계약 위반\n" + "\n".join(violations)
