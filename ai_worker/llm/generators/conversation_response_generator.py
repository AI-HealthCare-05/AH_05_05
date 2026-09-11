from typing import Any, Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ai_worker.domain.intake_display import format_active_medication_names
from ai_worker.llm.prompts.prompt_assets import load_prompt_template_document
from ai_worker.schemas.conversation_gate import ConversationIntent, SymptomFollowUpField


class ConversationResponseInput(BaseModel):
    """친근한 대화 또는 증상 문진 응답에 필요한 최소 입력이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1)
    intent: ConversationIntent
    follow_up_fields: list[SymptomFollowUpField] = Field(default_factory=list, max_length=3)
    active_medication_names: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class ConversationResponsePayload(BaseModel):
    """LLM이 작성하는 비의료적 응답 본문이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: str = Field(min_length=1)


class AsyncConversationResponseClient(Protocol):
    async def ainvoke(self, messages: Any) -> ConversationResponsePayload | dict[str, Any]: ...


PROMPT_DOCUMENT = load_prompt_template_document("conversation_response_prompt_v1.md")
PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", PROMPT_DOCUMENT.system),
        ("human", PROMPT_DOCUMENT.user),
    ]
)


class ConversationResponseGenerator:
    """대화형 질문에 제한된 LLM 문구와 서버 표시 섹션을 결합한다."""

    def __init__(self, *, client: AsyncConversationResponseClient) -> None:
        self._client = client

    async def generate(self, input: ConversationResponseInput) -> str:
        messages = PROMPT.format_messages(
            question=input.question,
            intent=input.intent.value,
            follow_up_fields=", ".join(field.value for field in input.follow_up_fields) or "없음",
        )
        payload = await self._client.ainvoke(messages)
        if not isinstance(payload, ConversationResponsePayload):
            payload = ConversationResponsePayload.model_validate(payload)
        return self._format_answer(input=input, body=payload.answer)

    def fallback(self, input: ConversationResponseInput) -> str:
        """모델 호출 실패 시에도 의학적 주장을 만들지 않는 짧은 응답이다."""

        bodies = {
            ConversationIntent.GREETING: "안녕하세요. 무엇을 도와드릴까요?",
            ConversationIntent.CASUAL: "그랬군요. 어떤 점이 가장 신경 쓰이는지 말씀해 주세요.",
            ConversationIntent.VAGUE_SYMPTOM: (
                "많이 불편하시겠어요. 어디가 언제부터 얼마나 아픈지 알려주실 수 있을까요?"
            ),
            ConversationIntent.SPECIFIC_SYMPTOM: (
                "증상이 시작된 시점과 통증 정도, 함께 나타나는 증상을 알려주세요."
            ),
        }
        return self._format_answer(input=input, body=bodies.get(input.intent, "무엇을 도와드릴까요?"))

    @staticmethod
    def _format_answer(*, input: ConversationResponseInput, body: str) -> str:
        normalized_body = " ".join(body.split())
        if input.intent is not ConversationIntent.SPECIFIC_SYMPTOM:
            return normalized_body

        sections: list[str] = []
        medication_names = format_active_medication_names(input.active_medication_names)
        if medication_names:
            sections.append("💊 **복약정보**\n" + "\n".join(f"- {name}" for name in medication_names))
        sections.append(f"🩺 **확인을 위해 필요한 정보**\n- {normalized_body}")
        return "\n\n".join(sections)


def build_conversation_response_generator(
    *,
    model: str,
    api_key: SecretStr | None = None,
    timeout_seconds: float = 5.0,
    max_retries: int = 0,
) -> ConversationResponseGenerator:
    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")

    client = ChatOpenAI(
        model=normalized_model,
        temperature=0,
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=max_retries,
    ).with_structured_output(
        ConversationResponsePayload,
        method="json_schema",
        strict=True,
    )
    return ConversationResponseGenerator(client=client)
