import re
import unicodedata

from ai_worker.schemas.knowledge import (
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    InteractionRuleFact,
    MedicationEvidenceCoverage,
    MedicationGuideLookup,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan


class MedicationEvidenceCoverageEvaluator:
    """질문 항목마다 답변에 사용할 수 있는 근거가 있는지 판정한다."""

    _SUPPORTED_SECTIONS = (
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.ADVERSE_EVENT,
        KnowledgeSectionType.INTERACTION,
    )
    _EMPTY_VALUES = {
        "",
        "-",
        "없음",
        "없습니다",
        "해당 없음",
        "해당없음",
        "자료 없음",
        "정보 없음",
    }

    def evaluate(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        guide_lookup: MedicationGuideLookup,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        approved_therapeutic_class_names: list[str] | None = None,
        crosscheck_chunks: list[RetrievedKnowledgeChunk] | None = None,
    ) -> MedicationEvidenceCoverage:
        requested = [section for section in self._SUPPORTED_SECTIONS if section in query_plan.section_types]
        covered = self._covered_non_interaction_sections(
            requested=requested,
            guide_lookup=guide_lookup,
            chunks=chunks,
        )
        verified_pair_keys = self._verified_interaction_pair_keys(
            query_plan=query_plan,
            rules=rules,
            chunks=chunks,
        )
        # 교차 확인 쌍은 전용 검색 결과로만 판정한다. 답변 근거(chunks)에는 섞지 않는다.
        verified_crosscheck_pair_keys = self._verified_crosscheck_pair_keys(
            query_plan=query_plan,
            rules=rules,
            chunks=crosscheck_chunks or [],
        )
        overview_supported = False
        if len(query_plan.entity_names) == 1 and not query_plan.interaction_pair_keys:
            subject = self._normalize(query_plan.entity_names[0])
            overview_supported = (
                any(
                    subject in {self._normalize(rule.left_name), self._normalize(rule.right_name)}
                    and any(self._has_value(text) for text in rule.effect_texts)
                    for rule in rules
                )
                or any(
                    chunk.metadata.section_type == KnowledgeSectionType.INTERACTION
                    and subject
                    in {
                        self._normalize(name) for name in [*chunk.metadata.drug_names, *chunk.metadata.ingredient_names]
                    }
                    and subject in self._normalize(chunk.content)
                    for chunk in chunks
                )
                or any(
                    chunk.metadata.document_type.value == "DRUG_ENCYCLOPEDIA"
                    and self._is_legacy_interaction_chunk(chunk)
                    and any(
                        self._normalize(class_name) in self._normalize(chunk.content)
                        for class_name in approved_therapeutic_class_names or []
                    )
                    and self._has_value(chunk.content)
                    for chunk in chunks
                )
            )
        if KnowledgeSectionType.INTERACTION in requested and (verified_pair_keys or overview_supported):
            covered.append(KnowledgeSectionType.INTERACTION)
        elif verified_crosscheck_pair_keys and KnowledgeSectionType.INTERACTION not in covered:
            # 질문이 상호작용을 요청하지 않았어도 등록 복용 항목과의 조합에서 근거를 확인했다면
            # 답변이 그 사실을 말할 수 있어야 한다. 확보 목록에 없으면 재작성이 초안의 칸을 지운다.
            covered.append(KnowledgeSectionType.INTERACTION)

        return MedicationEvidenceCoverage(
            requested_section_types=requested,
            covered_section_types=covered,
            missing_section_types=[section for section in requested if section not in covered],
            verified_interaction_pair_keys=verified_pair_keys,
            verified_crosscheck_pair_keys=verified_crosscheck_pair_keys,
        )

    def _verified_crosscheck_pair_keys(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[str]:
        """등록 복약정보와의 대조 쌍 중 근거로 확인된 것만 돌려준다."""
        requested_keys = set(query_plan.crosscheck_pair_keys)
        if not requested_keys:
            return []
        verified = requested_keys.intersection(rule.pair_key for rule in rules)
        for chunk in chunks:
            verified.update(requested_keys.intersection(chunk.metadata.interaction_pair_keys))
            if chunk.metadata.section_type != KnowledgeSectionType.INTERACTION:
                continue
            for pair in query_plan.crosscheck_pairs:
                if pair.pair_key in requested_keys and self._same_sentence_contains_pair(
                    chunk.content,
                    left_name=pair.left_name,
                    right_name=pair.right_name,
                ):
                    verified.add(pair.pair_key)
        return [key for key in query_plan.crosscheck_pair_keys if key in verified]

    @classmethod
    def _is_legacy_interaction_chunk(cls, chunk: RetrievedKnowledgeChunk) -> bool:
        compact_content = cls._normalize(chunk.content)
        return compact_content.startswith("상호작용") and any(
            marker in compact_content for marker in ("함께", "병용", "투여", "복용")
        )

    def _covered_non_interaction_sections(
        self,
        *,
        requested: list[KnowledgeSectionType],
        guide_lookup: MedicationGuideLookup,
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[KnowledgeSectionType]:
        available: set[KnowledgeSectionType] = {chunk.metadata.section_type for chunk in chunks}
        guide = guide_lookup.guide
        if guide is not None:
            if self._has_value(guide.efficacy):
                available.add(KnowledgeSectionType.FUNCTION)
            if self._has_value(guide.usage_instructions):
                available.add(KnowledgeSectionType.DAILY_INTAKE)
            if any(
                self._has_value(value)
                for value in (
                    guide.pre_use_warning,
                    guide.precautions,
                    guide.adverse_reactions,
                )
            ):
                available.add(KnowledgeSectionType.CAUTION)
            # 이상반응은 주의사항 근거에 포함되지만, 근거가 실제로 있을 때만 확보로 센다.
            # 함께 묶으면 이상반응 자료가 없는 제품에서 이상반응 섹션이 통과한다.
            if self._has_value(guide.adverse_reactions):
                available.add(KnowledgeSectionType.ADVERSE_EVENT)
        if any(
            self._has_value(value)
            for guides in guide_lookup.form_caution_guides.values()
            for guide in guides
            for value in (
                guide.pre_use_warning,
                guide.precautions,
                guide.adverse_reactions,
            )
        ):
            available.add(KnowledgeSectionType.CAUTION)

        if not requested:
            # 항목을 지정하지 않은 전반 설명 질문이다. 확보한 근거를 그대로 covered로 둔다.
            # 빈 목록으로 두면 답변이 어떤 섹션을 선언하든 근거 밖으로 판정해 초안이 그대로 나간다.
            return [
                section
                for section in self._SUPPORTED_SECTIONS
                if section != KnowledgeSectionType.INTERACTION and section in available
            ]
        covered = [
            section for section in requested if section != KnowledgeSectionType.INTERACTION and section in available
        ]
        # 화면의 주의사항과 이상반응은 같은 주의사항 근거에서 온다. 주의사항을 요청했는데
        # 이상반응만 확보에서 빠지면, 같은 질문도 표현에 따라 섹션 구성이 달라진다.
        # 이상반응 자료가 실제로 있을 때만 더한다.
        if (
            KnowledgeSectionType.CAUTION in covered
            and KnowledgeSectionType.ADVERSE_EVENT in available
            and KnowledgeSectionType.ADVERSE_EVENT not in covered
        ):
            covered.append(KnowledgeSectionType.ADVERSE_EVENT)
        return covered

    def _verified_interaction_pair_keys(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[str]:
        requested_keys = set(query_plan.interaction_pair_keys)
        if not requested_keys:
            return []

        verified = requested_keys.intersection(rule.pair_key for rule in rules)
        for chunk in chunks:
            chunk_keys = set(chunk.metadata.interaction_pair_keys)
            verified.update(requested_keys.intersection(chunk_keys))
            if chunk_keys or chunk.metadata.section_type != KnowledgeSectionType.INTERACTION:
                continue
            for pair in query_plan.interaction_pairs:
                if pair.pair_key not in requested_keys:
                    continue
                if self._same_sentence_contains_pair(
                    chunk.content,
                    left_name=pair.left_name,
                    right_name=pair.right_name,
                ):
                    verified.add(pair.pair_key)
        return [key for key in query_plan.interaction_pair_keys if key in verified]

    @classmethod
    def _same_sentence_contains_pair(
        cls,
        content: str,
        *,
        left_name: str,
        right_name: str,
    ) -> bool:
        left = cls._normalize(left_name)
        right = cls._normalize(right_name)
        return any(
            left in cls._normalize(sentence) and right in cls._normalize(sentence)
            for sentence in re.split(r"[.!?。！？\n]+", content)
            if sentence.strip()
        )

    @classmethod
    def _has_value(cls, value: str) -> bool:
        return value.strip() not in cls._EMPTY_VALUES

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[^0-9a-z가-힣]", "", normalized)
