from ai_worker.schemas.chat import (
    ChatAnswerRequest,
    ChatClassificationResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    ChatRoute,
)
from ai_worker.schemas.guideline import (
    GuidelineSearchQuery,
)


class ChatQueryBuilder:
    _TOPIC_BY_INTENT: dict[
        ChatIntent,
        str,
    ] = {
        ChatIntent.MEDICATION: "MEDICATION",
        ChatIntent.WARNING_SIGN: "WARNING_SIGN",
        ChatIntent.LIFESTYLE: "LIFESTYLE",
    }

    def build(
        self,
        request: ChatAnswerRequest,
        classification: ChatClassificationResult,
        limit: int = 5,
    ) -> GuidelineSearchQuery:
        if classification.route != ChatRoute.PATIENT_AND_RAG:
            raise ValueError("PATIENT_AND_RAG 경로에서만 공공자료 검색 질문을 생성할 수 있습니다.")

        normalized_query = classification.normalized_query

        if normalized_query is None:
            raise ValueError("공공자료 검색에 normalized_query가 필요합니다.")

        return GuidelineSearchQuery(
            query=normalized_query,
            condition=request.condition,
            care_phase=request.care_phase,
            topic=self._TOPIC_BY_INTENT.get(classification.intent),
            limit=limit,
        )
