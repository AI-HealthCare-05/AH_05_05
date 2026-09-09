from typing import Protocol

from ai_worker.schemas.medication_search_evaluation import RerankerEvaluationCandidate


class CandidateReranker(Protocol):
    """후보 집합을 보존한 채 순서만 조정하는 reranker 계약이다."""

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankerEvaluationCandidate],
    ) -> list[RerankerEvaluationCandidate]: ...


class DeterministicScoreCandidateReranker:
    """A/B 평가 전용 점수 adapter다. 실제 검색 경로에는 연결하지 않는다."""

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankerEvaluationCandidate],
    ) -> list[RerankerEvaluationCandidate]:
        del query
        indexed_candidates = list(enumerate(candidates))
        return [
            candidate
            for _, candidate in sorted(
                indexed_candidates,
                key=lambda item: (
                    item[1].reranker_score is not None,
                    item[1].reranker_score if item[1].reranker_score is not None else float("-inf"),
                    -item[0],
                ),
                reverse=True,
            )
        ]
