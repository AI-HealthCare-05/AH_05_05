import re

from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
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
    _GUIDE_PARENTHETICAL_GLOSS = re.compile(r"\s*\([^()]*\)")
    _GUIDE_RDB_SPACING = (
        ("감기로인한", "감기로 인한 "),
        ("발열및", "발열 및 "),
        ("에사용합니다", "에 사용합니다"),
        ("동통", "통증"),
    )

    def assemble(
        self,
        *,
        context: ActiveIntakeContext,
        guide: MedicationGuideFact | None,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
        interaction_question: bool,
        interaction_overview_subject: str | None = None,
        approved_therapeutic_class_names: list[str] | None = None,
        referenced_product_heading: str | None = None,
        family_reference: bool = False,
        ingredient_family_reference: bool = False,
        ingredient_family: SupplementIngredientFamily | None = None,
        unsupported_pairs: list[str] | None = None,
        question_interaction_pairs: list[MedicationInteractionQueryPair] | None = None,
        active_intake_interaction: bool = False,
        evidence_coverage: MedicationEvidenceCoverage | None = None,
        response_subject: str | None = None,
        adverse_reaction_question: bool = False,
        functional_goal_title: str | None = None,
        functional_goal_details: bool = False,
        form_caution_guides: dict[str, list[MedicationGuideFact]] | None = None,
        interaction_overview: bool = False,
    ) -> str:
        intake_sections = self._patient_intake_sections(context)
        sections: list[str] = []
        interaction_sections, has_unverified_interaction_notice = self._interaction_sections(
            rules=rules,
            chunks=chunks,
            interaction_question=interaction_question,
            question_interaction_pairs=question_interaction_pairs or [],
            active_intake_interaction=active_intake_interaction,
            interaction_overview_subject=interaction_overview_subject,
            evidence_coverage=evidence_coverage,
        )
        if interaction_overview:
            interaction_sections = self._interaction_overview_sections(rules=rules, chunks=chunks)
            has_unverified_interaction_notice = True
        sections.extend(interaction_sections)
        if guide is not None:
            sections.append(
                self._product_guide_section(
                    guide=guide,
                    family_reference=family_reference,
                    evidence_coverage=evidence_coverage,
                    adverse_reaction_question=adverse_reaction_question,
                )
            )
        form_caution_section = self._form_caution_section(
            form_caution_guides or {},
            response_subject=response_subject,
        )
        if form_caution_section:
            sections.append(form_caution_section)
        if chunks and not question_interaction_pairs and not form_caution_section and not interaction_overview:
            public_section = self._functional_goal_section(
                chunks=chunks,
                functional_goal_title=functional_goal_title,
                functional_goal_details=functional_goal_details,
            ) or self._public_knowledge_section(
                chunks=chunks,
                interaction_question=interaction_question,
                interaction_overview_subject=interaction_overview_subject,
                approved_therapeutic_class_names=approved_therapeutic_class_names or [],
                ingredient_family_reference=ingredient_family_reference,
                response_subject=response_subject,
                adverse_reaction_question=adverse_reaction_question,
                functional_goal_title=functional_goal_title,
                evidence_coverage=evidence_coverage,
            )
            sections.append(public_section)
        ingredient_family_section = self._ingredient_family_section(
            ingredient_family,
        )
        sections.extend(
            [ingredient_family_section] if ingredient_family_section else [],
        )
        unsupported_section = self._unsupported_pairs_section(
            unsupported_pairs or [],
        )
        if (
            unsupported_section
            and not has_unverified_interaction_notice
            and not active_intake_interaction
            and not interaction_overview_subject
        ):
            sections.append(unsupported_section)
            has_unverified_interaction_notice = True
        missing_section = self._missing_evidence_section(
            evidence_coverage,
            exclude_interaction=has_unverified_interaction_notice or bool(interaction_overview_subject),
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
    def _form_caution_section(
        cls,
        form_caution_guides: dict[str, list[MedicationGuideFact]],
        *,
        response_subject: str | None,
    ) -> str | None:
        if not form_caution_guides:
            return None
        sections = [f"**{response_subject or '성분'}**", "⚠️ **주의사항**"]
        for ingredient_name, guides in form_caution_guides.items():
            warnings = list(
                dict.fromkeys(
                    cls._clean_guide_value(value)
                    for guide in guides
                    for value in (
                        guide.pre_use_warning,
                        guide.precautions,
                        guide.adverse_reactions,
                    )
                    if cls._has_guide_value(value)
                )
            )
            if warnings:
                sections.append(
                    f"**{ingredient_name}**\n" + "\n".join(f"- {warning}" for warning in warnings[:3]),
                )
        return "\n\n".join(sections) if len(sections) > 2 else None

    @staticmethod
    def _functional_goal_section(
        *,
        chunks: list[RetrievedKnowledgeChunk],
        functional_goal_title: str | None,
        functional_goal_details: bool = False,
    ) -> str | None:
        if functional_goal_title is None:
            return None
        function_section = MedicationAnswerAssembler._named_functional_ingredient_sections(
            chunks,
            functional_goal_title=functional_goal_title,
            functional_goal_details=functional_goal_details,
        )
        if function_section is None:
            return None
        caution_lines = list(
            dict.fromkeys(
                f"- {chunk.metadata.ingredient_names[0]}: {' '.join(chunk.content.split())}"
                for chunk in chunks
                if chunk.metadata.section_type is KnowledgeSectionType.CAUTION
                and len(chunk.metadata.ingredient_names) == 1
            )
        )
        if caution_lines:
            return function_section + "\n\n⚠️ **주의사항**\n\n" + "\n".join(caution_lines)
        return function_section

    @staticmethod
    def _public_knowledge_section(
        *,
        chunks: list[RetrievedKnowledgeChunk],
        interaction_question: bool,
        interaction_overview_subject: str | None,
        approved_therapeutic_class_names: list[str],
        ingredient_family_reference: bool,
        response_subject: str | None,
        adverse_reaction_question: bool,
        functional_goal_title: str | None,
        evidence_coverage: MedicationEvidenceCoverage | None = None,
    ) -> str:
        public_lines = [f"- {chunk.content}" for chunk in chunks[:4]]
        if interaction_question:
            public_lines = MedicationAnswerAssembler._interaction_evidence_lines(
                chunks=chunks[:4],
                overview_subject=interaction_overview_subject,
                approved_class_names=approved_therapeutic_class_names,
            )
            return "검색된 상호작용 연구 근거\n" + "\n".join(public_lines)
        adverse_case_chunks = [
            chunk for chunk in chunks if chunk.metadata.document_type is KnowledgeDocumentType.ADVERSE_CASE_REPORT
        ]
        if adverse_reaction_question and adverse_case_chunks:
            return MedicationAnswerAssembler._adverse_case_report_section(
                adverse_case_chunks,
            )
        if ingredient_family_reference:
            public_lines.insert(
                0,
                (
                    "- 아래 내용은 단일제의 일반 정보입니다. 정확한 제품의 "
                    "성분·함량·제형에 따라 제품·복합제별 안내가 다를 수 "
                    "있으므로 제품명을 함께 확인하세요."
                ),
            )
            return "성분 계열 일반 정보\n" + "\n".join(public_lines)
        if not response_subject:
            if named_function_sections := MedicationAnswerAssembler._named_functional_ingredient_sections(
                chunks,
                functional_goal_title=functional_goal_title,
            ):
                return named_function_sections
            return "공공자료 추가 설명\n" + "\n".join(public_lines)

        sections = [f"**{response_subject}**"]
        section_headings = {
            KnowledgeSectionType.FUNCTION: "✅ **효능**",
            KnowledgeSectionType.DAILY_INTAKE: "✅ **복용법**",
            KnowledgeSectionType.CAUTION: ("🚨 **이상반응**" if adverse_reaction_question else "⚠️ **주의사항**"),
        }
        # 질문이 항목을 지정했으면 그 항목의 청크만 초안에 싣는다.
        # 주의사항은 예외로 항상 남긴다. 효능만 물었다는 이유로 금기를 지우면
        # 사용자는 주의사항이 없다고 읽게 되고, 이는 근거 부재를 안전으로 렌더링하는 것과 같다.
        # 안내사항 폴백도 같은 청크를 써야 걸러낸 내용이 원문으로 되돌아오지 않는다.
        covered = MedicationAnswerAssembler._covered_sections(evidence_coverage)
        allowed_chunks = [
            chunk
            for chunk in chunks[:4]
            if chunk.metadata.section_type is KnowledgeSectionType.CAUTION
            or MedicationAnswerAssembler._section_is_allowed(
                chunk.metadata.section_type,
                coverage=evidence_coverage,
                covered=covered,
            )
        ]
        for section_type in (
            KnowledgeSectionType.FUNCTION,
            KnowledgeSectionType.DAILY_INTAKE,
            KnowledgeSectionType.CAUTION,
        ):
            section_lines = [
                f"- {chunk.content}" for chunk in allowed_chunks if chunk.metadata.section_type is section_type
            ]
            if section_lines:
                sections.append(section_headings[section_type] + "\n" + "\n".join(section_lines))
        if len(sections) == 1 and allowed_chunks:
            sections.append("✉️ **안내사항**\n" + "\n".join(f"- {chunk.content}" for chunk in allowed_chunks))
        return "\n\n".join(sections)

    @staticmethod
    def _interaction_evidence_lines(
        *,
        chunks: list[RetrievedKnowledgeChunk],
        overview_subject: str | None,
        approved_class_names: list[str],
    ) -> list[str]:
        subject = re.sub(r"\s+", "", overview_subject or "").casefold()
        lines = []
        for chunk in chunks:
            content = re.sub(r"\s+", "", chunk.content).casefold()
            class_name = next(
                (
                    name
                    for name in approved_class_names
                    if subject not in content and re.sub(r"\s+", "", name).casefold() in content
                ),
                None,
            )
            prefix = f"[약물 계열 수준 근거: {class_name}] " if class_name else ""
            lines.append(f"- {prefix}{chunk.content}")
        return lines

    @staticmethod
    def _functional_ingredient_names(
        chunks: list[RetrievedKnowledgeChunk],
        *,
        limit: int,
    ) -> list[str]:
        ingredient_names: list[str] = []
        seen_names: set[str] = set()
        for chunk in chunks:
            if chunk.metadata.section_type is not KnowledgeSectionType.FUNCTION:
                continue
            for ingredient_name in chunk.metadata.ingredient_names:
                normalized_name = ingredient_name.strip()
                if not normalized_name or normalized_name.casefold() in seen_names:
                    continue
                seen_names.add(normalized_name.casefold())
                ingredient_names.append(normalized_name)
                if len(ingredient_names) == limit:
                    return ingredient_names
        return ingredient_names

    @staticmethod
    def _named_functional_ingredient_sections(
        chunks: list[RetrievedKnowledgeChunk],
        *,
        functional_goal_title: str | None = None,
        functional_goal_details: bool = False,
    ) -> str | None:
        """목표형 영양제 질문에는 검색된 성분명과 해당 기능을 함께 남긴다."""

        ingredient_names = MedicationAnswerAssembler._functional_ingredient_names(
            chunks,
            limit=3 if functional_goal_title == "건강 증진" else 4,
        )
        if not ingredient_names:
            return None
        if functional_goal_details:
            goal = "수면의 질 개선" if functional_goal_title == "숙면" else functional_goal_title
            return "\n\n".join(
                [
                    f"**{goal} 관련 기능성 원료**",
                    "💪🏻 **영양제 정보**\n"
                    + "\n".join(
                        f"- {name}: {MedicationAnswerAssembler._function_for_ingredient(chunks, name)}"
                        for name in ingredient_names[:3]
                    ),
                ]
            )
        if functional_goal_title:
            if functional_goal_title == "건강 증진":
                return "\n\n".join(
                    [
                        f"**{functional_goal_title}**",
                        "🧬 **성분**\n"
                        + "\n".join(
                            f"- {name}: {MedicationAnswerAssembler._function_for_ingredient(chunks, name)}"
                            for name in ingredient_names
                        ),
                    ]
                )
            return "\n\n".join(
                [
                    f"**{functional_goal_title}**",
                    "🧬 **성분**\n" + "\n".join(f"- {name}" for name in ingredient_names),
                ]
            )
        return "\n\n".join(f"**{name}**" for name in ingredient_names)

    @staticmethod
    def _function_for_ingredient(chunks: list[RetrievedKnowledgeChunk], ingredient_name: str) -> str:
        for chunk in chunks:
            if (
                ingredient_name not in chunk.metadata.ingredient_names
                or chunk.metadata.section_type is not KnowledgeSectionType.FUNCTION
            ):
                continue
            content = re.sub(rf"^{re.escape(ingredient_name)}(?:은|는|이|가)?\s*", "", chunk.content.strip())
            return re.sub(r"습니다\.?$", "음", content).rstrip(".")
        return "기능 정보를 확인함"

    @staticmethod
    def _adverse_case_report_section(
        chunks: list[RetrievedKnowledgeChunk],
    ) -> str:
        """이상사례 문서를 질문용 짧은 보고서 구조로 재배열한다."""

        chunks = [chunk for chunk in chunks if not chunk.metadata.is_adverse_assessment_reference]
        sections = ["🩻 **부작용 보고서**"]
        section_definitions = (
            (
                "**이상사례**",
                {KnowledgeSectionType.ADVERSE_EVENT},
                2,
            ),
            (
                "**추가설명**",
                {
                    KnowledgeSectionType.CASE_SUMMARY,
                    KnowledgeSectionType.ASSESSMENT,
                },
                3,
            ),
        )
        for heading, section_types, limit in section_definitions:
            lines = list(
                dict.fromkeys(f"- {chunk.content}" for chunk in chunks if chunk.metadata.section_type in section_types)
            )[:limit]
            if lines:
                sections.append(heading + "\n" + "\n".join(lines))

        if len(sections) == 1:
            sections.append("**이상사례**\n" + "\n".join(f"- {chunk.content}" for chunk in chunks[:2]))
        return "\n\n".join(sections)

    def _product_guide_section(
        self,
        *,
        guide: MedicationGuideFact,
        family_reference: bool,
        evidence_coverage: MedicationEvidenceCoverage | None,
        adverse_reaction_question: bool,
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
        if adverse_reaction_question:
            self._append_allowed_guide_section(
                guide_sections,
                heading="🚨 **이상반응**",
                value=guide.adverse_reactions,
                section_type=KnowledgeSectionType.CAUTION,
                evidence_coverage=evidence_coverage,
                covered=covered,
            )
            return "\n\n".join(guide_sections)
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
                "⚠️ **주의사항**\n" + "\n".join(self._caution_lines(value) for value in caution_values)
            )
        if evidence_coverage is None or not evidence_coverage.requested_section_types:
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
        interaction_overview_subject: str | None = None,
        evidence_coverage: MedicationEvidenceCoverage | None,
    ) -> tuple[list[str], bool]:
        sections: list[str] = []
        if interaction_overview_subject:
            if rules:
                return cls._overview_rule_sections(interaction_overview_subject, rules), False
            if not chunks:
                return [
                    f"**{interaction_overview_subject}**\n\n✉️ **안내사항**\n- 현재 근거에서 주의할 약·음식·영양제 목록을 확인하지 못했습니다."
                ], True
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
            if active_intake_interaction:
                return sections, False
            sections.append(cls._unverified_interaction_section())
            return sections, True
        return sections, False

    @classmethod
    def _interaction_overview_sections(
        cls,
        *,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[str]:
        groups: dict[str, list[str]] = {"🧬 **약과 상호작용**": [], "🍗 **그 외 상호작용**": []}
        for rule in rules:
            heading = "🧬 **약과 상호작용**" if rule.pair_type == "DRUG_DRUG" else "🍗 **그 외 상호작용**"
            groups[heading].extend(cls._rule_lines([rule]))
        for chunk in chunks:
            kind = chunk.metadata.interaction_type
            if kind == "DRUG_DRUG":
                heading = "🧬 **약과 상호작용**"
            elif kind in {"DRUG_SUPPLEMENT", "DRUG_FOOD", "SUPPLEMENT_SUPPLEMENT"} or chunk.metadata.food_names:
                heading = "🍗 **그 외 상호작용**"
            else:
                continue
            # 이름만으로 상호작용을 만들지 않고 해당 청크의 근거 문장을 요약 입력으로 보존한다.
            groups[heading].append("- " + re.sub(r"\s+", " ", chunk.content).strip())
        return [heading + "\n\n" + "\n".join(dict.fromkeys(lines)) for heading, lines in groups.items() if lines]

    @classmethod
    def _overview_rule_sections(cls, subject: str, rules: list[InteractionRuleFact]) -> list[str]:
        sections = [f"**{subject}**"]
        categories = {
            "DRUG_DRUG": "약물 상호작용",
            "DRUG_SUPPLEMENT": "영양제 상호작용",
            "DRUG_FOOD": "음식 상호작용",
        }
        grouped: dict[str, list[InteractionRuleFact]] = {}
        for rule in rules:
            grouped.setdefault(categories.get(rule.pair_type, "기타 상호작용"), []).append(rule)
        for title, items in grouped.items():
            caution = [
                rule for rule in items if rule.risk_level in {"CONTRAINDICATED", "HIGH_CAUTION", "CAUTION", "HIGH"}
            ]
            informational = [rule for rule in items if rule not in caution]
            parts = [f"🔁 **{title}**"]
            for label, values in [("주의가 필요한 조합", caution), ("참고할 상호작용", informational)]:
                if values:
                    parts.append(f"**{label}**\n" + "\n".join(cls._rule_lines(values)))
            sections.append("\n\n".join(parts))
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
        return f"- {prefix}{MedicationAnswerAssembler._clean_guide_value(value)}"

    @classmethod
    def _caution_lines(cls, value: str) -> str:
        """주의사항의 독립 조항을 각각의 bullet로 남긴다.

        한 덩어리로 합치면 초안에 수백 자짜리 bullet이 생기고, 재작성이 폴백되면
        그 원문이 그대로 화면에 나간다. 조항을 나눠도 내용은 버리지 않는다.
        효능은 `|`가 적응증 나열이라 같은 방식으로 나누지 않는다.
        """

        segments: list[str] = []
        for part in cls._clean_guide_value(value).split(", "):
            # 종결 어미 뒤의 마침표만 문장 경계로 본다. 용량 수치의 소수점은 나누지 않는다.
            segments.extend(segment.strip() for segment in re.split(r"(?<=[다요오])\.\s+", part) if segment.strip())
        unique = list(dict.fromkeys(segments))
        return "\n".join(f"- {segment}" for segment in unique) if unique else cls._guide_line("", value)

    @classmethod
    def _clean_guide_value(cls, value: str) -> str:
        """RDB의 구분 기호와 짧은 괄호 풀이를 읽기 쉬운 문장으로 정리한다."""

        parts = [part.strip() for part in value.split("|") if part.strip()]
        cleaned_parts = []
        for part in parts:
            cleaned = cls._GUIDE_PARENTHETICAL_GLOSS.sub("", part)
            for original, replacement in cls._GUIDE_RDB_SPACING:
                cleaned = cleaned.replace(original, replacement)
            cleaned_parts.append(re.sub(r"\s+", " ", cleaned).strip())
        return ", ".join(cleaned_parts) if cleaned_parts else value.strip()

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
        verified_pairs = [
            pair
            for pair in pairs
            if any(rule.pair_key == pair.pair_key for rule in rules) or pair.pair_key in verified_pair_keys
        ]
        if len(pairs) > 1 and not verified_pairs:
            return cls._unverified_interaction_section()

        lines = ["🔁 **질문 상호작용**"]
        for pair in verified_pairs or pairs:
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
        if verified_pairs and len(verified_pairs) != len(pairs):
            lines.extend(["", cls._unverified_interaction_section()])
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
        medication_lines = [
            f"- {MedicationAnswerAssembler._GUIDE_PARENTHETICAL_GLOSS.sub('', medication.name).strip()}"
            for medication in context.medications
        ]

        sections = []
        if medication_lines:
            sections.append("💊 **복약정보**\n" + "\n".join(medication_lines))

        supplement_lines = []
        for supplement in context.supplements:
            supplement_lines.append(f"- {supplement.name} · {supplement.dose_amount}{supplement.dose_unit}")
        if supplement_lines:
            sections.append("💪🏻 **영양제 정보**\n" + "\n".join(supplement_lines))
        return sections
