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
from ai_worker.schemas.medication_search import SupplementIngredientFamily

MEDICAL_DISCLAIMER = (
    "이 안내는 보유한 자료를 바탕으로 한 참고 정보이며 의료진의 진료, "
    "진단 또는 처방을 대체하지 않습니다. 복용 시작·중단·용량 변경은 "
    "의료진 또는 약사와 상의하세요."
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
        family_reference: bool = False,
        ingredient_family_reference: bool = False,
        ingredient_family: SupplementIngredientFamily | None = None,
        unsupported_pairs: list[str] | None = None,
        evidence_coverage: MedicationEvidenceCoverage | None = None,
    ) -> str:
        sections: list[str] = []
        patient_lines = self._patient_lines(context)
        if patient_lines:
            sections.append("사용자 확정 복약정보\n" + "\n".join(patient_lines))
        if rules:
            interaction_lines = [
                f"- {rule.left_name} ↔ {rule.right_name}: " + " ".join(rule.effect_texts) for rule in rules
            ]
            sections.append("확인된 상호작용\n" + "\n".join(interaction_lines))
        elif interaction_question and not chunks:
            sections.append(
                "확인된 상호작용\n"
                "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 "
                "확인하지 못했습니다. 확인되지 않았다는 뜻이지 안전하다는 "
                "뜻은 아닙니다."
            )
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
                section_title = "일반 제품 안내"
            sections.append(section_title + "\n" + "\n".join(guide_lines))
        if chunks:
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
        sections.extend([unsupported_section] if unsupported_section else [])
        missing_section = self._missing_evidence_section(evidence_coverage)
        sections.extend([missing_section] if missing_section else [])
        if not sections:
            sections.append(
                "현재 보유한 RDBMS와 공공자료에서 질문에 답할 근거를 "
                "찾지 못했습니다. 자료가 없다는 사실이 해당 제품이나 조합이 "
                "안전하다는 뜻은 아닙니다."
            )
        sections.append(MEDICAL_DISCLAIMER)
        return "\n\n".join(sections)

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
    ) -> str:
        if coverage is None or not coverage.missing_section_types:
            return ""
        labels = {
            KnowledgeSectionType.FUNCTION: "효능",
            KnowledgeSectionType.DAILY_INTAKE: "복용법",
            KnowledgeSectionType.CAUTION: "주의사항",
            KnowledgeSectionType.INTERACTION: "상호작용",
        }
        return "근거를 확인하지 못한 항목\n" + "\n".join(
            f"- {labels[section]}: 현재 근거에서 확인하지 못했습니다." for section in coverage.missing_section_types
        )

    @staticmethod
    def _unsupported_pairs_section(pairs: list[str]) -> str:
        if not pairs:
            return ""
        return "근거를 확인하지 못한 조합\n" + "\n".join(
            f"- {pair}: 현재 승인 규칙과 검색 근거에서 확인하지 "
            "못했습니다. 확인되지 않았다는 뜻이지 안전하다는 뜻은 "
            "아닙니다."
            for pair in pairs
        )

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
    def _patient_lines(context: ActiveIntakeContext) -> list[str]:
        lines = []
        for medication in context.medications:
            details = [medication.name]
            if medication.dose:
                details.append(medication.dose)
            if medication.times_per_day:
                details.append(f"1일 {medication.times_per_day}회")
            if medication.days:
                details.append(f"{medication.days}일")
            lines.append("- " + " · ".join(details))
        for supplement in context.supplements:
            lines.append(f"- {supplement.name} · {supplement.dose_amount}{supplement.dose_unit}")
        return lines
