from collections.abc import Callable

from ai_worker.schemas.knowledge import (
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan

RankKey = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], tuple[float, float, str]]
SectionTypes = Callable[[RetrievedKnowledgeChunk], set[KnowledgeSectionType]]


class MedicationKnowledgeRankingPolicy:
    """기존 점수 기준으로 정렬·중복 제거·다양성 선택을 수행합니다."""

    _MAX_CHUNKS_PER_DOCUMENT = 2

    def __init__(
        self,
        *,
        rank_key: RankKey,
        effective_section_types: SectionTypes,
        explicit_legacy_section_types: SectionTypes,
    ) -> None:
        self._rank_key = rank_key
        self._effective_section_types = effective_section_types
        self._explicit_legacy_section_types = explicit_legacy_section_types

    def rank(
        self,
        results: list[RetrievedKnowledgeChunk],
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> list[RetrievedKnowledgeChunk]:
        return sorted(
            self.deduplicate(results),
            key=lambda result: self._rank_key(result, plan),
            reverse=True,
        )

    @staticmethod
    def deduplicate(
        results: list[RetrievedKnowledgeChunk],
    ) -> list[RetrievedKnowledgeChunk]:
        unique: list[RetrievedKnowledgeChunk] = []
        seen_hashes: set[str] = set()
        for result in results:
            content_hash = result.metadata.content_hash
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            unique.append(result)
        return unique

    def select_diverse(
        self,
        results: list[RetrievedKnowledgeChunk],
        *,
        plan: MedicationKnowledgeQueryPlan,
        limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        selected: list[RetrievedKnowledgeChunk] = []
        selected_chunk_ids: set[str] = set()
        document_counts: dict[str, int] = {}
        # 하나의 공인 문서가 요청한 각 섹션을 각각 담을 수 있다. 이 경우
        # 문서 다양성 제한보다 섹션 커버리지를 우선해야 답변 항목이 누락되지 않는다.
        max_chunks_per_document = max(
            self._MAX_CHUNKS_PER_DOCUMENT,
            min(len(set(plan.section_types)), limit),
        )

        def add(result: RetrievedKnowledgeChunk) -> bool:
            if result.chunk_id in selected_chunk_ids:
                return False
            document_id = result.metadata.document_id
            count = document_counts.get(document_id, 0)
            if count >= max_chunks_per_document:
                return False
            selected.append(result)
            selected_chunk_ids.add(result.chunk_id)
            document_counts[document_id] = count + 1
            return True

        for section_type in plan.section_types:
            for explicit_only in (True, False):
                section_result = next(
                    (
                        result
                        for result in results
                        if result.chunk_id not in selected_chunk_ids
                        and section_type
                        in (
                            self._explicit_legacy_section_types(result)
                            if explicit_only
                            else self._effective_section_types(result)
                        )
                    ),
                    None,
                )
                if section_result is not None and add(section_result):
                    break
            if len(selected) >= limit:
                return selected

        for result in results:
            add(result)
            if len(selected) >= limit:
                break
        return selected
