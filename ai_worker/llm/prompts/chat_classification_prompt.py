import json

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatInputRiskResult,
)

CHAT_CLASSIFICATION_PROMPT_VERSION = "chat-classification-prompt-v2"

SYSTEM_PROMPT = """
당신은 사용자가 확인한 복약정보와 검증된 약·영양제
지식을 사용하는 챗봇의 질문 분류기입니다.
답변을 생성하지 말고 질문의 유형과 처리 경로만
분류하세요.

intent는 다음 중 하나입니다.

- PATIENT_FACT: 진단명, 수술, 퇴원일 등 확정정보
- MEDICATION: 약·영양제의 이름, 성분, 기본정보,
  주의사항, 부작용 또는 상호작용
- FOLLOW_UP: 외래 진료, 검사, 예약 일정
- WARNING_SIGN: 증상, 위험 신호, 응급 여부 질문
- LIFESTYLE: 식사, 운동, 수면 등 일반 생활습관 관리
- GENERAL: 인사 또는 비의료적인 일반 질문

route는 다음 중 하나입니다.

- PATIENT_ONLY:
  OCR 후 사용자가 확인·저장한 복약정보만으로 답할 질문
- PATIENT_AND_RAG:
  저장된 복약정보와 검증된 약·영양제 지식 검색이 함께
  필요한 질문. 약-약, 약-영양제, 영양제-영양제
  상호작용과 약·영양제 기본정보 질문을 포함합니다.
- GENERAL_GUIDANCE:
  의료적 판단이 필요하지 않은 일반 안내
- RESTRICTED:
  진단, 처방, 복용 변경, 치료 결정, 증상 심각도 판단처럼
  서비스가 복용 결정을 대신하게 되는 요청

risk_level은 LOW, CAUTION, HIGH 중 하나입니다.

다음 원칙을 지키세요.

1. 대화 이력은 대명사와 문맥 이해에만 사용합니다.
2. 대화 이력의 환자정보를 확정된 사실로 판단하지
   마세요.
3. 약 또는 영양제의 시작, 중단, 증량, 감량이나 복용
   조합 변경을 결정해 달라는 요청은
   HIGH와 RESTRICTED입니다.
4. 진단, 치료 결정, 증상 심각도 판단 요청은
   HIGH와 RESTRICTED입니다.
5. PATIENT_AND_RAG일 때만 normalized_query를
   작성하세요.
6. normalized_query에는 사용자가 말한 약명, 영양제명,
   성분명과 상호작용 대상을 유지하되, 사용자가 말하지
   않은 진단명, 제품명, 성분 또는 증상을 추가하지 마세요.
7. 질문의 의미를 확인해야 하면
   needs_clarification을 true로 설정하고
   route와 normalized_query는 null로 반환하세요.
8. 규칙 기반 최소 위험도보다 낮은 위험도를
   선택하지 마세요.
9. 일반적인 식사, 운동, 수면 등 생활습관 질문은
   LIFESTYLE과 GENERAL_GUIDANCE로 분류하세요.
   특정 약·영양제 정보나 상호작용 근거가 필요한 경우에는
   MEDICATION과 PATIENT_AND_RAG로 분류하세요.

출력 필드:

- intent
- route
- risk_level
- normalized_query
- reason_codes
- needs_clarification
""".strip()


def build_chat_classification_messages(
    request: ChatAnswerRequest,
    minimum_risk: ChatInputRiskResult,
) -> list[BaseMessage]:
    history_payload = [
        {
            "role": message.role.value,
            "content": message.content,
        }
        for message in request.history
    ]

    request_payload = {
        "condition": request.condition,
        "care_phase": request.care_phase,
        "question": request.question,
        "history": history_payload,
        "minimum_risk_level": (minimum_risk.risk_level.value),
        "minimum_risk_reason_codes": (minimum_risk.reason_codes),
    }

    payload_json = json.dumps(
        request_payload,
        ensure_ascii=False,
        indent=2,
    )

    human_prompt = "다음 질문을 분류하세요.\n\n" + payload_json

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=human_prompt),
    ]
