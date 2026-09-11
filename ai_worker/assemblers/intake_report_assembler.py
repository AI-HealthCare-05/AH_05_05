from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportCurrentStackItem,
    IntakeReportDataAvailability,
    IntakeReportDraft,
    IntakeReportEvidenceLevel,
    IntakeReportExecutiveSummary,
    IntakeReportItemType,
    IntakeReportProductGuide,
    IntakeReportReviewCard,
    IntakeReportReviewCardType,
    IntakeReportSource,
    IntakeReportUnverifiedItem,
    IntakeReportUnverifiedItemType,
)
from ai_worker.schemas.knowledge import RetrievedKnowledgeChunk
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    InteractionRuleFact,
    MedicationGuideLookup,
)


class IntakeReportAssembler:
    """Build report data deterministically before optional LLM wording."""

    _PAIR_TYPE_PRIORITY = {
        "DRUG_DRUG": 0,
        "DRUG_SUPPLEMENT": 1,
        "SUPPLEMENT_SUPPLEMENT": 2,
        "DRUG_FOOD": 3,
    }

    def assemble(
        self,
        *,
        context: ActiveIntakeContext,
        guide_lookups: list[MedicationGuideLookup],
        approved_rules: list[InteractionRuleFact],
        knowledge_chunks: list[RetrievedKnowledgeChunk],
        rag_available: bool,
    ) -> IntakeReportDraft:
        current_stack = self._current_stack(context)
        unverified_items = self._missing_amount_items(context)
        unverified_items.extend(self._ambiguous_guide_items(guide_lookups))
        if not rag_available:
            unverified_items.append(self._rag_unavailable_item())
        interaction_cards = self._interaction_cards(approved_rules)
        missing_info_cards = self._missing_info_cards(unverified_items)
        review_cards = [*interaction_cards, *missing_info_cards]
        sources = self._sources_from_rules(approved_rules)
        sources.extend(self._sources_from_chunks(knowledge_chunks))
        product_guides = self._product_guides(guide_lookups)
        executive_summary = self._executive_summary(
            current_stack=current_stack,
            review_cards=review_cards,
        )
        chart_data = self._chart_data(context, review_cards)
        data_availability = IntakeReportDataAvailability(
            active_medication_count=len(context.medications),
            active_supplement_count=len(context.supplements),
            approved_interaction_rule_available=bool(approved_rules),
            rag_evidence_available=rag_available and bool(knowledge_chunks),
        )
        deterministic_markdown = self._render_markdown(
            executive_summary=executive_summary,
            current_stack=current_stack,
            review_cards=review_cards,
            product_guides=product_guides,
            unverified_items=unverified_items,
            sources=sources,
        )
        return IntakeReportDraft(
            data_availability=data_availability,
            executive_summary=executive_summary,
            current_stack=current_stack,
            review_cards=review_cards,
            nutrient_totals=[],
            chart_data=chart_data,
            product_guides=product_guides,
            unverified_items=unverified_items,
            sources=sources,
            deterministic_markdown=deterministic_markdown,
        )

    @staticmethod
    def _current_stack(
        context: ActiveIntakeContext,
    ) -> list[IntakeReportCurrentStackItem]:
        medications = [
            IntakeReportCurrentStackItem(
                item_type=IntakeReportItemType.MEDICATION,
                item_id=medication.medication_id,
                product_name=medication.name,
                registered_intake_info=IntakeReportAssembler._medication_intake_info(
                    medication.dose,
                    medication.times_per_day,
                ),
                scheduled_slots=medication.scheduled_slots,
                evidence_level=IntakeReportEvidenceLevel.REGISTERED_INTAKE,
            )
            for medication in context.medications
        ]
        supplements = [
            IntakeReportCurrentStackItem(
                item_type=IntakeReportItemType.SUPPLEMENT,
                item_id=supplement.registration_id,
                product_name=supplement.name,
                ingredient_name=supplement.name,
                registered_intake_info=(
                    f"{supplement.dose_amount}{supplement.dose_unit}"
                    if supplement.dose_amount.strip()
                    else "등록된 복용량 확인 필요"
                ),
                scheduled_slots=supplement.scheduled_slots,
                evidence_level=IntakeReportEvidenceLevel.REGISTERED_INTAKE,
            )
            for supplement in context.supplements
        ]
        return [*medications, *supplements]

    @staticmethod
    def _medication_intake_info(
        dose: str | None,
        times_per_day: int | None,
    ) -> str:
        details = [dose.strip()] if dose and dose.strip() else []
        if times_per_day:
            details.append(f"1일 {times_per_day}회")
        return " · ".join(details) or "등록된 복용 정보 확인 필요"

    @staticmethod
    def _missing_amount_items(
        context: ActiveIntakeContext,
    ) -> list[IntakeReportUnverifiedItem]:
        return [
            IntakeReportUnverifiedItem(
                item_type=IntakeReportUnverifiedItemType.MISSING_AMOUNT,
                title=f"{supplement.name} 복용량 확인 필요",
                message=("등록된 복용량이 비어 있어 성분별 하루 총섭취량을 계산하지 않았습니다."),
                related_items=[supplement.name],
                next_step="제품 라벨의 1회 복용량과 하루 섭취 횟수를 확인해 주세요.",
            )
            for supplement in context.supplements
            if not supplement.dose_amount.strip()
        ]

    @staticmethod
    def _ambiguous_guide_items(
        guide_lookups: list[MedicationGuideLookup],
    ) -> list[IntakeReportUnverifiedItem]:
        return [
            IntakeReportUnverifiedItem(
                item_type=IntakeReportUnverifiedItemType.AMBIGUOUS_PRODUCT,
                title="의약품 제품명 확인 필요",
                message=("같은 이름으로 여러 제품이 확인되어 특정 제품 안내를 사실처럼 표시하지 않았습니다."),
                related_items=lookup.candidate_names,
                next_step="약봉투의 정확한 제품명과 성분명을 확인해 주세요.",
            )
            for lookup in guide_lookups
            if lookup.is_ambiguous
        ]

    @staticmethod
    def _rag_unavailable_item() -> IntakeReportUnverifiedItem:
        return IntakeReportUnverifiedItem(
            item_type=IntakeReportUnverifiedItemType.MISSING_EVIDENCE,
            title="추가 검색 근거 확인 필요",
            message=(
                "현재 보유한 추가 검색 근거를 확인하지 못했습니다. 확인하지 못한 사실이 안전하다는 뜻은 아닙니다."
            ),
            next_step="제품 라벨과 현재 복용 정보를 의료진 또는 약사에게 함께 확인해 주세요.",
        )

    def _interaction_cards(
        self,
        rules: list[InteractionRuleFact],
    ) -> list[IntakeReportReviewCard]:
        return [
            IntakeReportReviewCard(
                card_type=IntakeReportReviewCardType.INTERACTION,
                title=f"{rule.left_name} · {rule.right_name} 확인",
                summary=" ".join(rule.effect_texts),
                related_items=[rule.left_name, rule.right_name],
                check_item=("현재 복용 중인 제품 정보와 함께 의료진 또는 약사에게 확인해 주세요."),
                evidence_level=IntakeReportEvidenceLevel.APPROVED_RULE,
                sources=self._sources_from_rule(rule),
            )
            for rule in sorted(
                rules,
                key=lambda item: (
                    self._PAIR_TYPE_PRIORITY.get(item.pair_type, 99),
                    item.interaction_rule_id,
                ),
            )
        ]

    @staticmethod
    def _missing_info_cards(
        items: list[IntakeReportUnverifiedItem],
    ) -> list[IntakeReportReviewCard]:
        return [
            IntakeReportReviewCard(
                card_type=IntakeReportReviewCardType.MISSING_INFO,
                title=item.title,
                summary=item.message,
                related_items=item.related_items,
                check_item=item.next_step,
                evidence_level=IntakeReportEvidenceLevel.UNVERIFIED,
            )
            for item in items
        ]

    @staticmethod
    def _sources_from_rule(
        rule: InteractionRuleFact,
    ) -> list[IntakeReportSource]:
        if rule.source_references:
            return [
                IntakeReportSource(
                    title=source.title,
                    url=source.url,
                    evidence_level=IntakeReportEvidenceLevel.APPROVED_RULE,
                )
                for source in rule.source_references
            ]
        return [
            IntakeReportSource(
                title=title,
                url=(rule.source_urls[index] if index < len(rule.source_urls) else None),
                evidence_level=IntakeReportEvidenceLevel.APPROVED_RULE,
            )
            for index, title in enumerate(rule.source_titles)
        ]

    def _sources_from_rules(
        self,
        rules: list[InteractionRuleFact],
    ) -> list[IntakeReportSource]:
        return [source for rule in rules for source in self._sources_from_rule(rule)]

    @staticmethod
    def _sources_from_chunks(
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[IntakeReportSource]:
        return [
            IntakeReportSource(
                title=chunk.metadata.title,
                organization=chunk.metadata.provider,
                url=chunk.metadata.source_url,
                evidence_level=IntakeReportEvidenceLevel.RESEARCH,
            )
            for chunk in chunks
        ]

    @staticmethod
    def _product_guides(
        guide_lookups: list[MedicationGuideLookup],
    ) -> list[IntakeReportProductGuide]:
        return [
            IntakeReportProductGuide(
                product_name=lookup.guide.product_name,
                one_line_summary=(
                    lookup.guide.efficacy.strip() or "일반적인 역할을 현재 자료에서 확인하지 못했습니다."
                ),
                general_role=lookup.guide.efficacy.strip() or None,
                check_item=(lookup.guide.precautions.strip() or "제품별 주의사항을 현재 자료에서 확인하지 못했습니다."),
                sources=[
                    IntakeReportSource(
                        title=lookup.guide.product_name,
                        organization=lookup.guide.manufacturer_name,
                        evidence_level=IntakeReportEvidenceLevel.PUBLIC_GUIDE,
                    ),
                ],
            )
            for lookup in guide_lookups
            if lookup.guide is not None
        ]

    @staticmethod
    def _executive_summary(
        *,
        current_stack: list[IntakeReportCurrentStackItem],
        review_cards: list[IntakeReportReviewCard],
    ) -> IntakeReportExecutiveSummary:
        interaction_count = sum(card.card_type == IntakeReportReviewCardType.INTERACTION for card in review_cards)
        redundancy_count = sum(card.card_type == IntakeReportReviewCardType.REDUNDANCY for card in review_cards)
        return IntakeReportExecutiveSummary(
            reviewed_product_count=len(current_stack),
            potential_redundancy_count=redundancy_count,
            interaction_check_count=interaction_count,
            summary=(
                f"등록된 제품 {len(current_stack)}개를 확인했습니다. "
                f"승인된 상호작용 규칙 {interaction_count}건을 확인했습니다."
            ),
        )

    @staticmethod
    def _chart_data(
        context: ActiveIntakeContext,
        review_cards: list[IntakeReportReviewCard],
    ) -> IntakeReportChartData:
        return IntakeReportChartData(
            medication_count=len(context.medications),
            supplement_count=len(context.supplements),
            interaction_card_count=sum(
                card.card_type == IntakeReportReviewCardType.INTERACTION for card in review_cards
            ),
            redundancy_card_count=sum(card.card_type == IntakeReportReviewCardType.REDUNDANCY for card in review_cards),
            caution_card_count=sum(card.card_type == IntakeReportReviewCardType.CAUTION for card in review_cards),
            missing_info_card_count=sum(
                card.card_type == IntakeReportReviewCardType.MISSING_INFO for card in review_cards
            ),
        )

    @staticmethod
    def _render_markdown(
        *,
        executive_summary: IntakeReportExecutiveSummary,
        current_stack: list[IntakeReportCurrentStackItem],
        review_cards: list[IntakeReportReviewCard],
        product_guides: list[IntakeReportProductGuide],
        unverified_items: list[IntakeReportUnverifiedItem],
        sources: list[IntakeReportSource],
    ) -> str:
        sections = [
            "# 약·영양제 생활관리 보고서",
            "> 분석 기준: 현재 복용 중으로 등록된 약·영양제와 하루 복용 계획",
            "## 01. 한눈에 보는 분석 결과\n"
            "| 검토한 제품 | 중복 확인 항목 | 상호작용 확인 항목 |\n"
            "| ---: | ---: | ---: |\n"
            f"| {executive_summary.reviewed_product_count}개 | "
            f"{executive_summary.potential_redundancy_count}건 | "
            f"{executive_summary.interaction_check_count}건 |\n\n"
            f"{executive_summary.summary}",
        ]
        if review_cards:
            cards = "\n\n".join(
                "\n".join(
                    (
                        f"### {card.title}",
                        card.summary,
                        f"- 관련 제품·성분: {', '.join(card.related_items)}",
                        f"- 확인할 점: {card.check_item}",
                        f"- 근거: {card.evidence_level.value}",
                    )
                )
                for card in review_cards[:3]
            )
            sections.append("## 02. 먼저 확인해 주세요\n\n" + cards)
        if current_stack:
            rows = "\n".join(
                f"| {item.item_type.value} | {item.product_name} | "
                f"{item.ingredient_name or '-'} | {item.registered_intake_info} | "
                f"{', '.join(item.scheduled_slots) or '등록 시간 확인 필요'} |"
                for item in current_stack
            )
            sections.append(
                "## 03. 현재 등록한 약·영양제\n\n"
                "| 구분 | 제품명 | 주요 성분 | 등록된 복용 정보 | 등록된 시간 |\n"
                "| --- | --- | --- | --- | --- |\n"
                f"{rows}"
            )
        if product_guides:
            guide_text = "\n\n".join(
                "\n".join(
                    (
                        f"### {guide.product_name}",
                        f"> **한 줄 요약** {guide.one_line_summary}",
                        f"- 확인할 점: {guide.check_item}",
                    )
                )
                for guide in product_guides
            )
            sections.append("## 06. 제품별 역할과 생활관리 안내\n\n" + guide_text)
        if unverified_items:
            unverified_text = "\n\n".join(
                "\n".join(
                    (
                        f"### {item.title}",
                        item.message,
                        f"- 다음에 확인하면 좋은 정보: {item.next_step}",
                    )
                )
                for item in unverified_items
            )
            sections.append("## 07. 정보가 부족하거나 근거를 확인하지 못한 항목\n\n" + unverified_text)
        source_text = "\n".join(f"- {source.title}" for source in sources) or "- 현재 등록된 복용 정보"
        sections.append(
            "## 출처와 안내 한계\n\n"
            f"{source_text}\n\n"
            "이 보고서는 현재 등록된 정보와 보유한 근거를 바탕으로 한 참고용 안내입니다. "
            "복용 시작·중단·용량 변경이나 증상 판단은 의료진 또는 약사와 상의하세요."
        )
        return "\n\n".join(sections)
