from ai_worker.schemas.evidence_reasoning import EvidenceReasoningOutput
from ai_worker.schemas.knowledge import (
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    InteractionRuleFact,
    MedicationEvidenceCoverage,
    MedicationGuideFact,
)
from ai_worker.schemas.medication_search import (
    MedicationInteractionQueryPair,
    SupplementIngredientFamily,
)


class MedicationAnswerAssembler:
    _EMPTY_GUIDE_VALUES = {
        "",
        "-",
        "없음",
        "없습니다",
        "해당 없음",
        "해당없음",
        "자료 없음",
        "정보 없음",
    }

    def assemble(
        self,
        *,
        context: ActiveIntakeContext,
        guide: MedicationGuideFact | None,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        interaction_question: bool,
        referenced_product_heading: str | None = None,
        family_reference: bool = False,
        ingredient_family_reference: bool = False,
        ingredient_family: SupplementIngredientFamily | None = None,
        unsupported_pairs: list[str] | None = None,
        question_interaction_pairs: list[MedicationInteractionQueryPair] | None = None,
        active_intake_interaction: bool = False,
        evidence_coverage: MedicationEvidenceCoverage | None = None,
        evidence_reasoning: EvidenceReasoningOutput | None = None,
    ) -> str:
        intake_sections = self._patient_intake_sections(context)
        sections: list[str] = []
        interaction_sections = self._interaction_sections(
            rules=rules,
            chunks=chunks,
            interaction_question=interaction_question,
            question_interaction_pairs=question_interaction_pairs or [],
            active_intake_interaction=active_intake_interaction,
            evidence_coverage=evidence_coverage,
            evidence_reasoning=evidence_reasoning,
        )
        sections.extend(interaction_sections)
        if guide is not None:
            sections.append(
                self._product_guide_section(
                    guide=guide,
                    family_reference=family_reference,
                    evidence_coverage=evidence_coverage,
                )
            )
        if chunks and not question_interaction_pairs:
            public_lines = [f"- {chunk.content}" for chunk in chunks[:4]]
            if interaction_question:
                section_title = "검색된 상호작용 연구 근거"
            elif ingredient_family_reference:
                section_title = "성분 계열 일반 정보"
                public_lines.insert(
                    0,
                    (
                        "- 아래 내용은 단일제의 일반 정보입니다. 정확한 제품의 "
                        "성분·함량·제형에 따라 제품·복합제별 안내가 다를 수 "
                        "있으므로 제품명을 함께 확인하세요."
                    ),
                )
            else:
                section_title = "공공자료 추가 설명"
            sections.append(section_title + "\n" + "\n".join(public_lines))
        ingredient_family_section = self._ingredient_family_section(
            ingredient_family,
        )
        sections.extend(
            [ingredient_family_section] if ingredient_family_section else [],
        )
        missing_section = self._missing_evidence_section(
            evidence_coverage,
            exclude_interaction=True,
        )
        sections.extend([missing_section] if missing_section else [])
        if not sections:
            if interaction_question:
                sections.append("질문한 조합에 대한 직접 근거를 찾지 못했습니다.")
            else:
                sections.append(
                    "현재 보유한 RDBMS와 공공자료에서 질문에 답할 근거를 "
                    "찾지 못했습니다. 자료가 없다는 사실이 해당 제품이나 조합이 "
                    "안전하다는 뜻은 아닙니다."
                )
        if intake_sections and sections:
            return "\n\n".join([*intake_sections, "---", *sections])
        return "\n\n".join([*intake_sections, *sections])

    def _product_guide_section(
        self,
        *,
        guide: MedicationGuideFact,
        family_reference: bool,
        evidence_coverage: MedicationEvidenceCoverage | None,
    ) -> str:
        if family_reference:
            guide_lines = [f"- 기준 제품: {guide.product_name} ({guide.manufacturer_name})"]
            guide_lines.extend(
                (
                    self._guide_line("효능", guide.efficacy),
                    (
                        "- 주의사항: 같은 통칭의 제품이라도 제품별 "
                        "성분·함량·제형과 복용법이 다를 수 있으므로 "
                        "정확한 제품명을 확인해 주세요."
                    ),
                )
            )
            return "통칭 제품 참고 안내\n" + "\n".join(guide_lines)

        covered = self._covered_sections(evidence_coverage)
        guide_sections = [f"**{guide.product_name}**"]
        self._append_allowed_guide_section(
            guide_sections,
            heading="✅ **효능**",
            value=guide.efficacy,
            section_type=KnowledgeSectionType.FUNCTION,
            evidence_coverage=evidence_coverage,
            covered=covered,
        )
        self._append_allowed_guide_section(
            guide_sections,
            heading="✅ **복용법**",
            value=guide.usage_instructions,
            section_type=KnowledgeSectionType.DAILY_INTAKE,
            evidence_coverage=evidence_coverage,
            covered=covered,
        )
        caution_values = [
            value
            for value in (guide.pre_use_warning, guide.precautions)
            if self._guide_value_is_allowed(
                value,
                KnowledgeSectionType.CAUTION,
                coverage=evidence_coverage,
                covered=covered,
            )
        ]
        if caution_values:
            guide_sections.append(
                "⚠️ **주의사항**\n" + "\n".join(self._guide_line("", value) for value in caution_values)
            )
        self._append_allowed_guide_section(
            guide_sections,
            heading="🚨 **이상반응**",
            value=guide.adverse_reactions,
            section_type=KnowledgeSectionType.CAUTION,
            evidence_coverage=evidence_coverage,
            covered=covered,
        )
        self._append_allowed_guide_section(
            guide_sections,
            heading="🔁 **함께 주의할 약·음식**",
            value=guide.drug_food_interactions,
            section_type=KnowledgeSectionType.INTERACTION,
            evidence_coverage=evidence_coverage,
            covered=covered,
        )
        return "\n\n".join(guide_sections)

    def _append_allowed_guide_section(
        self,
        sections: list[str],
        *,
        heading: str,
        value: str,
        section_type: KnowledgeSectionType,
        evidence_coverage: MedicationEvidenceCoverage | None,
        covered: set[KnowledgeSectionType],
    ) -> None:
        if self._guide_value_is_allowed(
            value,
            section_type,
            coverage=evidence_coverage,
            covered=covered,
        ):
            sections.append(heading + "\n" + self._guide_line("", value))

    @classmethod
    def _interaction_sections(
        cls,
        *,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        interaction_question: bool,
        question_interaction_pairs: list[MedicationInteractionQueryPair],
        active_intake_interaction: bool,
        evidence_coverage: MedicationEvidenceCoverage | None,
        evidence_reasoning: EvidenceReasoningOutput | None,
    ) -> list[str]:
        sections: list[str] = []
        question_pair_keys = {pair.pair_key for pair in question_interaction_pairs}
        question_rules = [rule for rule in rules if rule.pair_key in question_pair_keys]
        active_intake_rules = [rule for rule in rules if rule.pair_key not in question_pair_keys]
        if active_intake_rules:
            sections.append("🔁 **복약정보와 상호작용**\n" + "\n".join(cls._rule_lines(active_intake_rules)))
        elif rules:
            sections.append("🔁 **확인된 상호작용**\n" + "\n".join(cls._rule_lines(rules)))

        question_section = cls._question_interaction_section(
            pairs=question_interaction_pairs,
            rules=question_rules,
            chunks=chunks,
            evidence_coverage=evidence_coverage,
            evidence_reasoning=evidence_reasoning,
        )
        if question_section:
            sections.append(question_section)
        elif interaction_question and not rules:
            heading = "🔁 **복약정보와 상호작용**" if active_intake_interaction else "🔁 **질문 상호작용**"
            sections.append(heading + "\n- 질문한 조합에 대한 직접 근거를 찾지 못했습니다.")
        return sections

    @staticmethod
    def _rule_lines(rules: list[InteractionRuleFact]) -> list[str]:
        return [f"- {rule.left_name} ↔ {rule.right_name}: " + " ".join(rule.effect_texts) for rule in rules]

    @classmethod
    def _has_guide_value(cls, value: str) -> bool:
        return value.strip() not in cls._EMPTY_GUIDE_VALUES

    @staticmethod
    def _guide_line(label: str, value: str) -> str:
        prefix = f"{label}: " if label else ""
        return f"- {prefix}{value.strip()}"

    @classmethod
    def _guide_value_is_allowed(
        cls,
        value: str,
        section_type: KnowledgeSectionType | None,
        *,
        coverage: MedicationEvidenceCoverage | None,
        covered: set[KnowledgeSectionType],
    ) -> bool:
        return cls._has_guide_value(value) and cls._section_is_allowed(
            section_type,
            coverage=coverage,
            covered=covered,
        )

    @staticmethod
    def _covered_sections(
        coverage: MedicationEvidenceCoverage | None,
    ) -> set[KnowledgeSectionType]:
        return set(coverage.covered_section_types) if coverage else set()

    @staticmethod
    def _section_is_allowed(
        section_type: KnowledgeSectionType | None,
        *,
        coverage: MedicationEvidenceCoverage | None,
        covered: set[KnowledgeSectionType],
    ) -> bool:
        if coverage is None or not coverage.requested_section_types:
            return True
        return section_type in covered

    @staticmethod
    def _missing_evidence_section(
        coverage: MedicationEvidenceCoverage | None,
        *,
        exclude_interaction: bool = False,
    ) -> str:
        if coverage is None or not coverage.missing_section_types:
            return ""
        labels = {
            KnowledgeSectionType.FUNCTION: "효능",
            KnowledgeSectionType.DAILY_INTAKE: "복용법",
            KnowledgeSectionType.CAUTION: "주의사항",
            KnowledgeSectionType.INTERACTION: "상호작용",
        }
        missing_sections = [
            section
            for section in coverage.missing_section_types
            if not (exclude_interaction and section is KnowledgeSectionType.INTERACTION)
        ]
        if not missing_sections:
            return ""
        return "근거를 확인하지 못한 항목\n" + "\n".join(
            f"- {labels[section]}: 현재 근거에서 확인하지 못했습니다." for section in missing_sections
        )

    @classmethod
    def _question_interaction_section(
        cls,
        *,
        pairs: list[MedicationInteractionQueryPair],
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        evidence_coverage: MedicationEvidenceCoverage | None,
        evidence_reasoning: EvidenceReasoningOutput | None,
    ) -> str:
        if not pairs:
            return ""

        verified_pair_keys = set(evidence_coverage.verified_interaction_pair_keys if evidence_coverage else [])
        reasoning_lines_by_pair = cls._reasoning_lines_by_pair(evidence_reasoning)
        verified_pairs = [
            pair
            for pair in pairs
            if (
                any(rule.pair_key == pair.pair_key for rule in rules)
                or pair.pair_key in verified_pair_keys
                or pair.pair_key in reasoning_lines_by_pair
            )
        ]
        if not verified_pairs:
            if len(pairs) > 1:
                return "🔁 **질문 상호작용**\n- 질문한 조합에 대한 직접 근거를 찾지 못했습니다."
            pair = pairs[0]
            return "\n".join(
                [
                    "🔁 **질문 상호작용**",
                    "",
                    f"**[{pair.left_name}-{pair.right_name}]**",
                    "- 질문한 조합에 대한 직접 근거를 찾지 못했습니다.",
                ]
            )

        lines = ["🔁 **질문 상호작용**"]
        for pair in verified_pairs:
            lines.extend(["", f"**[{pair.left_name}-{pair.right_name}]**"])
            pair_rules = [rule for rule in rules if rule.pair_key == pair.pair_key]
            if pair_rules:
                lines.extend(f"- {' '.join(rule.effect_texts)}" for rule in pair_rules)
            elif pair.pair_key in reasoning_lines_by_pair:
                lines.extend(f"- {statement}" for statement in reasoning_lines_by_pair[pair.pair_key])
            elif pair.pair_key in verified_pair_keys:
                lines.extend(
                    f"- {chunk.content}"
                    for chunk in chunks[:4]
                    if pair.pair_key in chunk.metadata.interaction_pair_keys
                )
        return "\n".join(lines)

    @staticmethod
    def _reasoning_lines_by_pair(
        evidence_reasoning: EvidenceReasoningOutput | None,
    ) -> dict[str, list[str]]:
        if evidence_reasoning is None:
            return {}
        lines_by_pair: dict[str, list[str]] = {}
        for claim in evidence_reasoning.claims:
            if claim.section_type is not KnowledgeSectionType.INTERACTION or claim.pair_key is None:
                continue
            lines_by_pair.setdefault(claim.pair_key, []).append(claim.statement)
        return lines_by_pair

    @staticmethod
    def _ingredient_family_section(
        family: SupplementIngredientFamily | None,
    ) -> str:
        if family is None:
            return ""
        members = ", ".join(family.member_names)
        return (
            "세부 성분 안내\n"
            f"- {family.canonical_name}는 여러 성분을 묶어 부르는 이름입니다. "
            "성분마다 기능·섭취량·주의사항이 다를 수 있습니다.\n"
            f"- 선택 가능한 성분: {members}\n"
            "- 정확한 섭취량, 주의사항 또는 상호작용이 필요하면 위 목록의 "
            "성분명을 포함해 다시 질문해 주세요."
        )

    @staticmethod
    def _patient_intake_sections(context: ActiveIntakeContext) -> list[str]:
        medication_lines = [f"- {medication.name}" for medication in context.medications]

        sections = []
        if medication_lines:
            sections.append("💊 **복약정보**\n" + "\n".join(medication_lines))

        supplement_lines = []
        for supplement in context.supplements:
            supplement_lines.append(f"- {supplement.name} · {supplement.dose_amount}{supplement.dose_unit}")
        if supplement_lines:
            sections.append("💪🏻 **영양제 정보**\n" + "\n".join(supplement_lines))
        return sections
