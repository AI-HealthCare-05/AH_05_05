import json
from typing import Any, Protocol

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ai_worker.llm.prompts.prompt_assets import load_prompt_template_document
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.conversation_gate import ConversationClassification

CONVERSATION_GATE_PROMPT_VERSION = "conversation-gate-prompt-v1"


class ConversationGateInput(BaseModel):
    """같은 세션의 대화만 제한적으로 전달하는 Conversation Gate 입력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1)
    recent_history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class ConversationGateChain(Protocol):
    async def ainvoke(
        self,
        input: ConversationGateInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> ConversationClassification: ...


class AsyncConversationGateClient(Protocol):
    async def ainvoke(self, messages: Any) -> ConversationClassification | dict[str, Any]: ...


PROMPT_DOCUMENT = load_prompt_template_document("conversation_gate_prompt_v1.md")
PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", PROMPT_DOCUMENT.system),
        ("human", PROMPT_DOCUMENT.user),
    ]
)


def build_conversation_gate_chain(
    *,
    model: str,
    api_key: SecretStr | None = None,
    timeout_seconds: float = 5.0,
    max_retries: int = 0,
    max_history_messages: int = 4,
    client: AsyncConversationGateClient | None = None,
) -> ConversationGateChain:
    """엔터티 없는 대화를 위한 제한된 구조화 분류 체인을 생성한다."""

    normalized_model = model.strip()
    if not normalized_model:
        raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")
    if max_history_messages < 0:
        raise ValueError("최근 대화 최대 개수는 음수일 수 없습니다.")

    response_runnable: Runnable
    if client is not None:
        response_runnable = RunnableLambda(client.ainvoke).with_config(
            run_name="conversation.gate.client",
        )
    else:
        response_runnable = (
            ChatOpenAI(
                model=normalized_model,
                temperature=0,
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
            .with_structured_output(
                ConversationClassification,
                method="json_schema",
                strict=True,
            )
            .with_config(run_name="conversation.gate.model")
        )

    def validate_input(value: ConversationGateInput | dict[str, Any]) -> ConversationGateInput:
        if isinstance(value, ConversationGateInput):
            return value
        return ConversationGateInput.model_validate(value)

    def render_prompt(value: ConversationGateInput):
        history = value.recent_history[-max_history_messages:] if max_history_messages else []
        return PROMPT.format_messages(
            question=value.question,
            history_json=json.dumps(
                [message.model_dump(mode="json") for message in history],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    def validate_output(value: ConversationClassification | dict[str, Any]) -> ConversationClassification:
        if isinstance(value, ConversationClassification):
            return value
        return ConversationClassification.model_validate(value)

    return (
        RunnableLambda(validate_input).with_config(run_name="conversation.gate.input")
        | RunnableLambda(render_prompt).with_config(run_name="conversation.gate.prompt")
        | response_runnable
        | RunnableLambda(validate_output).with_config(run_name="conversation.gate.output")
    ).with_types(
        input_type=ConversationGateInput,
        output_type=ConversationClassification,
    )
