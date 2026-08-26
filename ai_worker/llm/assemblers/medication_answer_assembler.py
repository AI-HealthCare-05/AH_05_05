from ai_worker.schemas.knowledge import RetrievedKnowledgeChunk
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    InteractionRuleFact,
    MedicationGuideFact,
)

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
        elif interaction_question:
            sections.append(
                "확인된 상호작용\n"
                "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 "
                "확인하지 못했습니다. 확인되지 않았다는 뜻이지 안전하다는 "
                "뜻은 아닙니다."
            )
        if guide is not None:
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
                    for label, value in (
                        ("효능", guide.efficacy),
                        ("사용법", guide.usage_instructions),
                        ("사용 전 확인", guide.pre_use_warning),
                        ("주의사항", guide.precautions),
                        ("함께 주의할 약·음식", guide.drug_food_interactions),
                        ("이상반응", guide.adverse_reactions),
                        ("보관법", guide.storage_instructions),
                    )
                    if self._has_guide_value(value)
                )
                section_title = "일반 제품 안내"
            sections.append(section_title + "\n" + "\n".join(guide_lines))
        if chunks:
            public_lines = [f"- {chunk.content}" for chunk in chunks[:4]]
            sections.append("공공자료 추가 설명\n" + "\n".join(public_lines))
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
