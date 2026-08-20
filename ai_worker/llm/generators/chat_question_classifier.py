from typing import Any, Protocol

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.llm.prompts.chat_classification_prompt import (
    build_chat_classification_messages,
)
from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatClassificationResult,
    ChatInputRiskResult,
)
from ai_worker.schemas.enums import (
    ChatRiskLevel,
    ChatRoute,
)


class ChatClassificationError(RuntimeError):
    """질문 분류 호출 또는 응답 검증 실패."""


class AsyncClassificationClient(Protocol):
    async def ainvoke(
        self,
        messages: Any,
    ) -> ChatClassificationResult | dict[str, Any]: ...


class OpenAIChatQuestionClassifier:
    _RISK_PRIORITY = {
        ChatRiskLevel.LOW: 0,
        ChatRiskLevel.CAUTION: 1,
        ChatRiskLevel.HIGH: 2,
    }

    def __init__(
        self,
        model: str,
        api_key: SecretStr | None = None,
        client: AsyncClassificationClient | None = None,
    ) -> None:
        normalized_model = model.strip()

        if not normalized_model:
            raise ValueError("LLM 모델명은 비어 있을 수 없습니다.")

        self._model_name = normalized_model

        if client is not None:
            self._client = client
            return

        chat_model = ChatOpenAI(
            model=normalized_model,
            temperature=0,
            api_key=api_key,
        )

        self._client = chat_model.with_structured_output(
            ChatClassificationResult,
            method="json_schema",
            strict=True,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    async def classify(
        self,
        request: ChatAnswerRequest,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        messages = build_chat_classification_messages(
            request=request,
            minimum_risk=minimum_risk,
        )

        try:
            response = await self._client.ainvoke(messages)

            if isinstance(
                response,
                ChatClassificationResult,
            ):
                classification = response
            else:
                classification = ChatClassificationResult.model_validate(response)
        except Exception as error:
            raise ChatClassificationError("챗봇 질문 분류에 실패했습니다.") from error

        return self._merge_minimum_risk(
            classification=classification,
            minimum_risk=minimum_risk,
        )

    @classmethod
    def _merge_minimum_risk(
        cls,
        classification: ChatClassificationResult,
        minimum_risk: ChatInputRiskResult,
    ) -> ChatClassificationResult:
        final_risk = max(
            (
                classification.risk_level,
                minimum_risk.risk_level,
            ),
            key=cls._RISK_PRIORITY.__getitem__,
        )

        reason_codes = list(
            dict.fromkeys(
                [
                    *minimum_risk.reason_codes,
                    *classification.reason_codes,
                ]
            )
        )

        update_data: dict[str, Any] = {
            "risk_level": final_risk,
            "reason_codes": reason_codes,
        }

        if final_risk == ChatRiskLevel.HIGH:
            update_data.update(
                {
                    "route": ChatRoute.RESTRICTED,
                    "normalized_query": None,
                    "needs_clarification": False,
                }
            )

        return classification.model_copy(
            update=update_data,
            deep=True,
        )
