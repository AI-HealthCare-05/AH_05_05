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

CHAT_CLASSIFICATION_PROMPT_VERSION = "chat-classification-prompt-v1"

SYSTEM_PROMPT = """
당신은 퇴원 환자 챗봇의 질문 분류기입니다.
답변을 생성하지 말고 질문의 유형과 처리 경로만
분류하세요.

intent는 다음 중 하나입니다.

- PATIENT_FACT: 진단명, 수술, 퇴원일 등 확정정보
- MEDICATION: 약 이름, 용량, 횟수, 복용 방법
- FOLLOW_UP: 외래 진료, 검사, 예약 일정
- WARNING_SIGN: 증상, 위험 신호, 응급 여부 질문
- LIFESTYLE: 식사, 운동, 수면, 일상생활 관리
- GENERAL: 인사 또는 비의료적인 일반 질문

route는 다음 중 하나입니다.

- PATIENT_ONLY:
  환자 확정정보만으로 답변할 수 있는 질문
- PATIENT_AND_RAG:
  환자정보와 공공 가이드라인이 함께 필요한 질문
- GENERAL_GUIDANCE:
  의료적 판단이 필요하지 않은 일반 안내
- RESTRICTED:
  진단, 약 변경, 치료 결정, 증상 심각도 판단 요청

risk_level은 LOW, CAUTION, HIGH 중 하나입니다.

다음 원칙을 지키세요.

1. 대화 이력은 대명사와 문맥 이해에만 사용합니다.
2. 대화 이력의 환자정보를 확정된 사실로 판단하지
   마세요.
3. 약 시작, 중단, 증량, 감량 또는 복용 변경 요청은
   HIGH와 RESTRICTED입니다.
4. 진단, 치료 결정, 증상 심각도 판단 요청은
   HIGH와 RESTRICTED입니다.
5. PATIENT_AND_RAG일 때만 normalized_query를
   작성하세요.
6. normalized_query에는 사용자가 말하지 않은
   진단명, 약물명 또는 증상을 추가하지 마세요.
7. 질문의 의미를 확인해야 하면
   needs_clarification을 true로 설정하고
   route와 normalized_query는 null로 반환하세요.
8. 규칙 기반 최소 위험도보다 낮은 위험도를
   선택하지 마세요.

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
