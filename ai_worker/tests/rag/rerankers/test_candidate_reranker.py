from ai_worker.rag.rerankers.candidate_reranker import DeterministicScoreCandidateReranker
from ai_worker.schemas.medication_search_evaluation import RerankerEvaluationCandidate


def test_deterministic_score_reranker_reorders_candidates_without_adding_or_dropping_documents() -> None:
    candidates = [
        RerankerEvaluationCandidate(document_id="doc-a", reranker_score=0.3),
        RerankerEvaluationCandidate(document_id="doc-b", reranker_score=0.9),
        RerankerEvaluationCandidate(document_id="doc-c", reranker_score=None),
    ]

    reranked = DeterministicScoreCandidateReranker().rerank(
        query="마그네슘의 효능",
        candidates=candidates,
    )

    assert [candidate.document_id for candidate in reranked] == ["doc-b", "doc-a", "doc-c"]
    assert {candidate.document_id for candidate in reranked} == {candidate.document_id for candidate in candidates}
