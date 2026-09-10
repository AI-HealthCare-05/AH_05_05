"""카탈로그 후보를 바꾸지 않고 질문 경로만 보조 분류하는 계약."""

import asyncio
import math
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_worker.schemas.medication_chat import MedicationChatRoute
from ai_worker.schemas.medication_search import MedicationQuestionConfidence

ROUTE_PROTOTYPES: dict[MedicationChatRoute, str] = {
    MedicationChatRoute.MEDICATION_GUIDE: "의약품의 효능 복용법 용법 주의사항을 묻는 질문",
    MedicationChatRoute.SUPPLEMENT_GUIDE: "영양성분의 역할 일반 섭취량 주의사항을 묻는 질문",
    MedicationChatRoute.INTERACTION: "약 영양제 음식 성분을 함께 먹어도 되는지 상호작용을 묻는 질문",
    MedicationChatRoute.ACTIVE_INTAKE: "등록한 복용약과 영양제 전체를 정리하거나 서로 확인하는 질문",
    MedicationChatRoute.GENERAL_GUIDANCE: "약과 영양제의 일반적인 생활 관리 정보를 묻는 질문",
}


class QuestionRoutingStage(StrEnum):
    """질문 경로를 제안한 단계."""

    RULE = "RULE"
    SEMANTIC = "SEMANTIC"
    LLM = "LLM"
    FALLBACK = "FALLBACK"


class QuestionRoutingReasonCode(StrEnum):
    """자유 형식 추론 대신 기록하는 최소 진단 코드."""

    SEMANTIC_ROUTE_MATCHED = "SEMANTIC_ROUTE_MATCHED"
    SCORE_BELOW_THRESHOLD = "SCORE_BELOW_THRESHOLD"
    MARGIN_BELOW_THRESHOLD = "MARGIN_BELOW_THRESHOLD"
    ROUTER_UNAVAILABLE = "ROUTER_UNAVAILABLE"


class SemanticRouterInput(BaseModel):
    """로컬 Router에 전달하는 비식별 질문 분류 입력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1)
    candidate_count: int = Field(default=0, ge=0)
    has_session_reference: bool = False

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()


class QuestionRoutingDecision(BaseModel):
    """후속 서버 검증에 쓸 구조화 경로 제안이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: QuestionRoutingStage
    route: MedicationChatRoute | None = None
    confidence: MedicationQuestionConfidence
    top_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    second_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    reason_codes: list[QuestionRoutingReasonCode] = Field(default_factory=list)

    @classmethod
    def semantic(
        cls,
        *,
        route: MedicationChatRoute,
        top_score: float,
        second_score: float,
    ) -> "QuestionRoutingDecision":
        return cls(
            stage=QuestionRoutingStage.SEMANTIC,
            route=route,
            confidence=MedicationQuestionConfidence.HIGH,
            top_score=top_score,
            second_score=second_score,
            reason_codes=[QuestionRoutingReasonCode.SEMANTIC_ROUTE_MATCHED],
        )

    @classmethod
    def fallback(
        cls,
        *,
        top_score: float | None,
        second_score: float | None,
        reason_codes: list[QuestionRoutingReasonCode],
    ) -> "QuestionRoutingDecision":
        return cls(
            stage=QuestionRoutingStage.FALLBACK,
            confidence=MedicationQuestionConfidence.LOW,
            top_score=top_score,
            second_score=second_score,
            reason_codes=reason_codes,
        )


class SemanticQuestionRouter(Protocol):
    async def ainvoke(
        self,
        input: SemanticRouterInput,
        **kwargs: Any,
    ) -> QuestionRoutingDecision | dict[str, Any]: ...


class QuestionEmbeddingModel(Protocol):
    """로컬 Router가 사용할 동기 임베딩 모델의 최소 계약."""

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class SemanticRouterUnavailableError(RuntimeError):
    """배포 이미지에 로컬 Router 모델이 준비되지 않았을 때 발생한다."""


class SentenceTransformerQuestionEmbeddingModel:
    """요청 중 네트워크를 사용하지 않는 process-local 임베딩 어댑터."""

    def __init__(self, *, model_name: str) -> None:
        normalized_model_name = model_name.strip()
        if not normalized_model_name:
            raise ValueError("Semantic Router 모델명은 비어 있을 수 없습니다.")
        self._model_name = normalized_model_name
        self._model: Any | None = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        model = self._model_or_raise()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def _model_or_raise(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_name,
                local_files_only=True,
            )
        except Exception as exc:  # pragma: no cover - depends on local model cache
            raise SemanticRouterUnavailableError(
                "Semantic Router 모델이 배포 이미지에 준비되지 않았습니다.",
            ) from exc
        return self._model


class LocalSemanticQuestionRouter:
    """질문의 경로만 제안하는 로컬 semantic router.

    이 클래스는 후보 엔터티·검색 섹션·상호작용 쌍을 반환하지 않는다. 따라서
    결과를 적용하더라도 제품명 및 안전성 결정은 기존 결정론적 체인이 담당한다.
    """

    def __init__(
        self,
        *,
        embedder: QuestionEmbeddingModel,
        min_score: float,
        min_margin: float,
        route_prototypes: dict[MedicationChatRoute, str] | None = None,
    ) -> None:
        if not -1.0 <= min_score <= 1.0:
            raise ValueError("Semantic Router 최소 점수는 -1.0 이상 1.0 이하여야 합니다.")
        if not 0.0 <= min_margin <= 2.0:
            raise ValueError("Semantic Router 최소 마진은 0.0 이상 2.0 이하여야 합니다.")
        self._embedder = embedder
        self._min_score = min_score
        self._min_margin = min_margin
        self._route_prototypes = route_prototypes or ROUTE_PROTOTYPES

    async def ainvoke(
        self,
        input: SemanticRouterInput,
        **_: Any,
    ) -> QuestionRoutingDecision:
        routes = list(self._route_prototypes)
        prototype_texts = [self._route_prototypes[route] for route in routes]
        vectors = await asyncio.to_thread(
            self._embedder.encode,
            [input.question, *prototype_texts],
        )
        if len(vectors) != len(routes) + 1:
            raise ValueError("Semantic Router 임베딩 수가 입력 수와 일치하지 않습니다.")
        ranked = sorted(
            (
                (route, self._cosine_similarity(vectors[0], vector))
                for route, vector in zip(routes, vectors[1:], strict=True)
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        top_route, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else -1.0
        if top_score < self._min_score:
            return QuestionRoutingDecision.fallback(
                top_score=top_score,
                second_score=second_score,
                reason_codes=[QuestionRoutingReasonCode.SCORE_BELOW_THRESHOLD],
            )
        if top_score - second_score < self._min_margin:
            return QuestionRoutingDecision.fallback(
                top_score=top_score,
                second_score=second_score,
                reason_codes=[QuestionRoutingReasonCode.MARGIN_BELOW_THRESHOLD],
            )
        return QuestionRoutingDecision.semantic(
            route=top_route,
            top_score=top_score,
            second_score=second_score,
        )

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            raise ValueError("Semantic Router 임베딩 차원이 유효하지 않습니다.")
        denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
            sum(value * value for value in right),
        )
        if denominator == 0:
            return -1.0
        return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True)) / denominator
