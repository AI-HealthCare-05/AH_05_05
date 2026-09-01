import re
import unicodedata

from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeEvidenceLevel,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)


class KnowledgeSearchResultRefiner:
    """Qdrant 후보를 중복 제거하고 질문의 명시적 어휘로 재정렬한다."""

    _MIN_EXACT_TITLE_LENGTH = 4
    _TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]+")
    _EVIDENCE_PRIORITY = {
        KnowledgeEvidenceLevel.REGULATORY: 7,
        KnowledgeEvidenceLevel.SYSTEMATIC_REVIEW: 6,
        KnowledgeEvidenceLevel.REVIEW_ARTICLE: 5,
        KnowledgeEvidenceLevel.CLINICAL_STUDY: 4,
        KnowledgeEvidenceLevel.OBSERVATIONAL_STUDY: 3,
        KnowledgeEvidenceLevel.CASE_REPORT: 2,
        KnowledgeEvidenceLevel.PRECLINICAL: 1,
        KnowledgeEvidenceLevel.UNKNOWN: 0,
    }

    @classmethod
    def refine(
        cls,
        results: list[RetrievedKnowledgeChunk],
        *,
        query: str,
        limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        deduplicated = cls._deduplicate(results)
        normalized_query = cls._compact(query)
        query_tokens = cls._tokens(query)
        title_matches = {
            result.chunk_id: cls._title_is_explicit_in_normalized_query(
                result.metadata.title,
                normalized_query,
            )
            for result in deduplicated
        }
        exact_titles = {
            cls._compact(result.metadata.title) for result in deduplicated if title_matches[result.chunk_id]
        }
        if exact_titles:
            deduplicated = [result for result in deduplicated if cls._compact(result.metadata.title) in exact_titles]

        ranked = sorted(
            deduplicated,
            key=lambda result: cls._ranking_key(
                result,
                query_tokens=query_tokens,
                title_matches=title_matches,
            ),
            reverse=True,
        )
        return ranked[:limit]

    @classmethod
    def _deduplicate(
        cls,
        results: list[RetrievedKnowledgeChunk],
    ) -> list[RetrievedKnowledgeChunk]:
        representatives: dict[
            tuple[
                KnowledgeSectionType,
                tuple[str, ...],
                tuple[str, ...],
                str,
            ],
            RetrievedKnowledgeChunk,
        ] = {}
        for result in results:
            key = cls._semantic_key(result)
            current = representatives.get(key)
            if current is None or cls._is_better_representative(
                result,
                current,
            ):
                representatives[key] = result
        return list(representatives.values())

    @classmethod
    def _semantic_key(
        cls,
        result: RetrievedKnowledgeChunk,
    ) -> tuple[
        KnowledgeSectionType,
        tuple[str, ...],
        tuple[str, ...],
        str,
    ]:
        return (
            result.metadata.section_type,
            tuple(sorted(cls._compact(name) for name in result.metadata.drug_names)),
            tuple(sorted(cls._compact(name) for name in result.metadata.ingredient_names)),
            cls._compact(result.content),
        )

    @classmethod
    def _is_better_representative(
        cls,
        candidate: RetrievedKnowledgeChunk,
        current: RetrievedKnowledgeChunk,
    ) -> bool:
        candidate_priority = cls._representative_priority(candidate)
        current_priority = cls._representative_priority(current)
        if candidate_priority != current_priority:
            return candidate_priority > current_priority
        return candidate.metadata.document_id < current.metadata.document_id

    @classmethod
    def _representative_priority(
        cls,
        result: RetrievedKnowledgeChunk,
    ) -> tuple[int, int]:
        return (
            cls._EVIDENCE_PRIORITY[result.metadata.evidence_level],
            int(result.metadata.access_scope == KnowledgeAccessScope.PUBLIC),
        )

    @classmethod
    def _ranking_key(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        query_tokens: set[str],
        title_matches: dict[str, bool],
    ) -> tuple[int, int, float, str]:
        metadata_tokens = cls._tokens(
            " ".join(
                [
                    result.metadata.title,
                    result.metadata.section_title or "",
                    *result.metadata.drug_names,
                    *result.metadata.ingredient_names,
                ]
            )
        )
        return (
            int(title_matches[result.chunk_id]),
            len(query_tokens.intersection(metadata_tokens)),
            result.similarity_score,
            result.chunk_id,
        )

    @classmethod
    def _title_is_explicit_in_query(
        cls,
        title: str,
        query: str,
    ) -> bool:
        return cls._title_is_explicit_in_normalized_query(
            title,
            cls._compact(query),
        )

    @classmethod
    def _title_is_explicit_in_normalized_query(
        cls,
        title: str,
        normalized_query: str,
    ) -> bool:
        title_anchors = cls._tokens(title)
        return any(
            len(anchor) >= cls._MIN_EXACT_TITLE_LENGTH and anchor in normalized_query for anchor in title_anchors
        )

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        return {
            token.casefold()
            for token in cls._TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", value))
            if len(token) >= 2
        }

    @staticmethod
    def _compact(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return "".join(character for character in normalized if character.isalnum())
