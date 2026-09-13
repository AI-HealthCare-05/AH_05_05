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
        evidence_coverage: MedicationEvidenceCoverage | None = None,
    ) -> str:
        intake_sections = self._patient_intake_sections(context)
        sections: list[str] = []
        interaction_sections, has_unverified_interaction_notice = self._interaction_sections(
            rules=rules,
            chunks=chunks,
            interaction_question=interaction_question,
            question_interaction_pairs=question_interaction_pairs or [],
            evidence_coverage=evidence_coverage,
        )
        sections.extend(interaction_sections)
        if guide is not None:
            covered = self._covered_sections(evidence_coverage)
            guide_lines = [
                (
                    f"- 기준 제품: {guide.product_name} ({guide.manufacturer_name})"
                    if family_reference
                    else f"- 제품: {guide.product_name} ({guide.manufacturer_name})"
                ),
            ]
            if family_reference:
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
                section_title = "통칭 제품 참고 안내"
            else:
                guide_lines.extend(
                    self._guide_line(label, value)
                    for label, value, section_type in (
                        (
                            "효능",
                            guide.efficacy,
                            KnowledgeSectionType.FUNCTION,
                        ),
                        (
                            "사용법",
                            guide.usage_instructions,
                            KnowledgeSectionType.DAILY_INTAKE,
                        ),
                        (
                            "사용 전 확인",
                            guide.pre_use_warning,
                            KnowledgeSectionType.CAUTION,
                        ),
                        (
                            "주의사항",
                            guide.precautions,
                            KnowledgeSectionType.CAUTION,
                        ),
                        (
                            "함께 주의할 약·음식",
                            guide.drug_food_interactions,
                            KnowledgeSectionType.INTERACTION,
                        ),
                        (
                            "이상반응",
                            guide.adverse_reactions,
                            KnowledgeSectionType.CAUTION,
                        ),
                        (
                            "보관법",
                            guide.storage_instructions,
                            None,
                        ),
                    )
                    if self._has_guide_value(value)
                    and self._section_is_allowed(
                        section_type,
                        coverage=evidence_coverage,
                        covered=covered,
                    )
                )
                section_title = referenced_product_heading or "일반 제품 안내"
            sections.append(section_title + "\n" + "\n".join(guide_lines))
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
        unsupported_section = self._unsupported_pairs_section(
            unsupported_pairs or [],
        )
        if unsupported_section and not has_unverified_interaction_notice:
            sections.append(unsupported_section)
            has_unverified_interaction_notice = True
        missing_section = self._missing_evidence_section(
            evidence_coverage,
            exclude_interaction=has_unverified_interaction_notice,
        )
        sections.extend([missing_section] if missing_section else [])
        if not sections:
            sections.append(
                "현재 보유한 RDBMS와 공공자료에서 질문에 답할 근거를 "
                "찾지 못했습니다. 자료가 없다는 사실이 해당 제품이나 조합이 "
                "안전하다는 뜻은 아닙니다."
            )
        if intake_sections and sections:
            return "\n\n".join([*intake_sections, "---", *sections])
        return "\n\n".join([*intake_sections, *sections])

    @classmethod
    def _interaction_sections(
        cls,
        *,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        interaction_question: bool,
        question_interaction_pairs: list[MedicationInteractionQueryPair],
        evidence_coverage: MedicationEvidenceCoverage | None,
    ) -> tuple[list[str], bool]:
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
        )
        if question_section:
            sections.append(question_section)
            return (
                sections,
                cls._has_unverified_question_interaction(
                    pairs=question_interaction_pairs,
                    rules=question_rules,
                    evidence_coverage=evidence_coverage,
                ),
            )
        if interaction_question and not chunks and not rules:
            sections.append(cls._unverified_interaction_section())
            return sections, True
        return sections, False

    @staticmethod
    def _rule_lines(rules: list[InteractionRuleFact]) -> list[str]:
        return [f"- {rule.left_name} ↔ {rule.right_name}: " + " ".join(rule.effect_texts) for rule in rules]

    @classmethod
    def _has_guide_value(cls, value: str) -> bool:
        return value.strip() not in cls._EMPTY_GUIDE_VALUES

    @staticmethod
    def _guide_line(label: str, value: str) -> str:
        return f"- {label}: {value.strip()}"

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

    @staticmethod
    def _unsupported_pairs_section(pairs: list[str]) -> str:
        if not pairs:
            return ""
        return MedicationAnswerAssembler._unverified_interaction_section()

    @staticmethod
    def _unverified_interaction_section() -> str:
        return (
            "☑️ **확인하지 못한 조합**\n"
            "현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 "
            "못했습니다. 확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다."
        )

    @classmethod
    def _question_interaction_section(
        cls,
        *,
        pairs: list[MedicationInteractionQueryPair],
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        evidence_coverage: MedicationEvidenceCoverage | None,
    ) -> str:
        if not pairs:
            return ""

        verified_pair_keys = set(evidence_coverage.verified_interaction_pair_keys if evidence_coverage else [])
        lines = ["🔁 **질문 상호작용**"]
        for pair in pairs:
            lines.extend(["", f"**[{pair.left_name}-{pair.right_name}]**"])
            pair_rules = [rule for rule in rules if rule.pair_key == pair.pair_key]
            if pair_rules:
                lines.extend(f"- {' '.join(rule.effect_texts)}" for rule in pair_rules)
            elif pair.pair_key in verified_pair_keys:
                lines.extend(
                    f"- {chunk.content}"
                    for chunk in chunks[:4]
                    if pair.pair_key in chunk.metadata.interaction_pair_keys
                )
            else:
                lines.append(
                    "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 "
                    "못했습니다. 확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다."
                )
        return "\n".join(lines)

    @staticmethod
    def _has_unverified_question_interaction(
        *,
        pairs: list[MedicationInteractionQueryPair],
        rules: list[InteractionRuleFact],
        evidence_coverage: MedicationEvidenceCoverage | None,
    ) -> bool:
        if not pairs:
            return False
        verified_pair_keys = set(evidence_coverage.verified_interaction_pair_keys if evidence_coverage else [])
        rule_pair_keys = {rule.pair_key for rule in rules}
        return any(pair.pair_key not in rule_pair_keys and pair.pair_key not in verified_pair_keys for pair in pairs)

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
