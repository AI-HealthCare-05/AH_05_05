import re

import pytest

from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.medication_search import (
    MedicationCatalogEntry,
    MedicationExpressionResolutionStatus,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
    MedicationQuestionScope,
)


class StaticExpressionCatalog:
    def __init__(self, expressions: list[str]) -> None:
        self.expressions = expressions
        self.call_count = 0

    async def list_expressions(self) -> list[str]:
        self.call_count += 1
        return self.expressions


class StaticTypedExpressionCatalog(StaticExpressionCatalog):
    def __init__(self, entries: list[MedicationCatalogEntry]) -> None:
        super().__init__([entry.canonical_name for entry in entries])
        self.entries = entries

    async def list_entries(self) -> list[MedicationCatalogEntry]:
        return self.entries


class CountingEditDistanceResolver(RuleBasedMedicationQuestionResolver):
    edit_distance_call_count = 0

    @staticmethod
    def _edit_distance(left: str, right: str, *, limit: int) -> int:
        CountingEditDistanceResolver.edit_distance_call_count += 1
        return RuleBasedMedicationQuestionResolver._edit_distance(
            left,
            right,
            limit=limit,
        )


class CountingBigramResolver(RuleBasedMedicationQuestionResolver):
    bigram_call_count = 0

    @staticmethod
    def _bigrams(value: str) -> set[str]:
        CountingBigramResolver.bigram_call_count += 1
        return RuleBasedMedicationQuestionResolver._bigrams(value)


@pytest.mark.asyncio
async def test_resolver_auto_corrects_unique_product_typo() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["타이레놀", "아세트아미노펜"]),
    )

    result = await resolver.resolve(
        question="타이래놀의 효능과 주의사항을 알려줘",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "타이레놀의 효능과 주의사항을 알려줘"
    assert result.corrections[0].original == "타이래놀"
    assert result.corrections[0].replacement == "타이레놀"


@pytest.mark.asyncio
async def test_resolver_preserves_catalog_entity_type_and_source() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticTypedExpressionCatalog(
            [
                MedicationCatalogEntry(
                    canonical_name="테스트성분",
                    aliases=["테스트별칭"],
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.DRUG,
                    source=MedicationQueryEntitySource.RDBMS,
                )
            ]
        ),
    )

    result = await resolver.resolve(question="테스트별칭의 주의사항을 알려줘")

    assert result.entity_resolution_available is True
    assert len(result.entities) == 1
    assert result.entities[0].canonical_name == "테스트성분"
    assert result.entities[0].entity_type == MedicationQueryEntityType.INGREDIENT_NAME
    assert result.entities[0].kind == InteractionEntityKind.DRUG
    assert result.entities[0].source == MedicationQueryEntitySource.RDBMS


@pytest.mark.asyncio
async def test_resolver_matches_typed_food_alias_from_catalog() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticTypedExpressionCatalog(
            [
                MedicationCatalogEntry(
                    canonical_name="펙소페나딘",
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.DRUG,
                    source=MedicationQueryEntitySource.RDBMS,
                ),
                MedicationCatalogEntry(
                    canonical_name="과일주스",
                    aliases=["자몽주스"],
                    entity_type=MedicationQueryEntityType.FOOD_CATEGORY,
                    kind=InteractionEntityKind.FOOD,
                    source=MedicationQueryEntitySource.QDRANT,
                ),
            ]
        ),
    )

    result = await resolver.resolve(
        question="펙소페나딘을 먹을 때 자몽주스를 피해야 하나요?",
    )

    assert result.status == MedicationExpressionResolutionStatus.UNCHANGED
    assert [(entity.canonical_name, entity.kind, entity.source) for entity in result.entities] == [
        ("펙소페나딘", InteractionEntityKind.DRUG, MedicationQueryEntitySource.RDBMS),
        ("과일주스", InteractionEntityKind.FOOD, MedicationQueryEntitySource.QDRANT),
    ]


@pytest.mark.asyncio
async def test_resolver_preserves_active_intake_entity_source() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticTypedExpressionCatalog([]),
    )

    result = await resolver.resolve(
        question="등록약의 복용법을 알려줘",
        additional_entities=[
            MedicationCatalogEntry(
                canonical_name="등록약",
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=InteractionEntityKind.DRUG,
                source=MedicationQueryEntitySource.PATIENT_CONTEXT,
            )
        ],
    )

    assert result.entity_resolution_available is True
    assert result.entities[0].canonical_name == "등록약"
    assert result.entities[0].source == MedicationQueryEntitySource.PATIENT_CONTEXT


@pytest.mark.asyncio
async def test_resolver_auto_corrects_bare_unique_product_typo() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["타이레놀", "아세트아미노펜"]),
    )

    result = await resolver.resolve(question="타이래놀")

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "타이레놀"


@pytest.mark.asyncio
async def test_resolver_auto_corrects_trailing_keyboard_typo() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["타이레놀", "마그네슘"]),
    )

    result = await resolver.resolve(
        question="타이레놀ㄹ 복용법 알려줘",
    )

    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "타이레놀 복용법 알려줘"


@pytest.mark.asyncio
async def test_resolver_matches_latin_letter_and_compatibility_jamo_only_from_catalog() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticTypedExpressionCatalog(
            [
                MedicationCatalogEntry(
                    canonical_name="비타민 D",
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.SUPPLEMENT,
                    source=MedicationQueryEntitySource.RDBMS,
                ),
                MedicationCatalogEntry(
                    canonical_name="타이레놀",
                    entity_type=MedicationQueryEntityType.BRAND_ALIAS,
                    kind=InteractionEntityKind.DRUG,
                    source=MedicationQueryEntitySource.RDBMS,
                ),
            ]
        ),
    )

    vitamin = await resolver.resolve(question="비타민 디의 주의사항을 알려줘")
    jamo = await resolver.resolve(question="ㅌㅏㅇㅣㄹㅔㄴㅗㄹ 복용법 알려줘")

    assert [entity.canonical_name for entity in vitamin.entities] == ["비타민 D"]
    assert [entity.canonical_name for entity in jamo.entities] == ["타이레놀"]


@pytest.mark.asyncio
async def test_resolver_records_source_backed_normalization_diagnostics() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticTypedExpressionCatalog(
            [
                MedicationCatalogEntry(
                    canonical_name="비타민 D",
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.SUPPLEMENT,
                    source=MedicationQueryEntitySource.QDRANT,
                )
            ]
        ),
    )

    result = await resolver.resolve(question="비타민 디의 주의사항을 알려줘")

    assert result.normalization_strategy.value == "LETTER_PRONUNCIATION"
    assert result.confidence_tier.value == "HIGH"
    assert result.shortlisted_candidate_count == 1
    assert result.tie_count == 0
    assert result.relation_resolution_status.value == "NOT_APPLICABLE"
    assert result.catalog_source_counts == {"QDRANT": 1}
    assert result.catalog_type_counts == {"INGREDIENT_NAME": 1}


@pytest.mark.asyncio
async def test_resolver_shortlists_typo_candidates_before_edit_distance() -> None:
    CountingEditDistanceResolver.edit_distance_call_count = 0
    unrelated_expressions = [f"제품{i:05d}정" for i in range(5_000)]
    resolver = CountingEditDistanceResolver(
        catalog=StaticExpressionCatalog(
            ["타이레놀", *unrelated_expressions],
        ),
    )

    result = await resolver.resolve(
        question="타이레놀ㄹ 복용법 알려줘",
    )

    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "타이레놀 복용법 알려줘"
    assert CountingEditDistanceResolver.edit_distance_call_count < 100


@pytest.mark.asyncio
async def test_resolver_does_not_regex_scan_entire_multiword_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regex_search_call_count = 0
    original_search = re.search

    def counting_search(*args: object, **kwargs: object) -> re.Match[str] | None:
        nonlocal regex_search_call_count
        regex_search_call_count += 1
        return original_search(*args, **kwargs)

    monkeypatch.setattr(re, "search", counting_search)
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(
            [
                "타이레놀",
                *(f"검색 대상이 아닌 제품 {index:05d}" for index in range(5_000)),
            ],
        ),
    )

    result = await resolver.resolve(
        question="타이래놀의 효능과 주의사항을 알려줘",
    )

    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "타이레놀의 효능과 주의사항을 알려줘"
    assert regex_search_call_count < 100


@pytest.mark.asyncio
async def test_resolver_reuses_candidate_indexes_for_cached_catalog() -> None:
    CountingBigramResolver.bigram_call_count = 0
    resolver = CountingBigramResolver(
        catalog=StaticExpressionCatalog(
            [
                "타이레놀",
                *(f"제품{index:05d}정" for index in range(1_000)),
            ],
        ),
    )

    first = await resolver.resolve(question="타이래놀 복용법 알려줘")
    first_call_count = CountingBigramResolver.bigram_call_count
    second = await resolver.resolve(question="타이래놀 복용법 알려줘")
    repeated_call_count = CountingBigramResolver.bigram_call_count - first_call_count

    assert first.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert second.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert repeated_call_count < 20


@pytest.mark.asyncio
async def test_resolver_uses_same_rule_for_other_ingredients() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["아세트아미노펜", "마그네슘"]),
    )

    result = await resolver.resolve(
        question="아세트아미노팬 부작용 알려줘",
    )

    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "아세트아미노펜 부작용 알려줘"


@pytest.mark.asyncio
async def test_resolver_restores_spacing_only_when_joined_expression_is_known() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["마그네슘"]),
    )

    result = await resolver.resolve(
        question="마그 네슘은 왜 먹나요?",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "마그네슘은 왜 먹나요?"
    assert result.corrections[0].original == "마그 네슘"
    assert result.corrections[0].replacement == "마그네슘"


@pytest.mark.asyncio
async def test_resolver_keeps_correct_multiword_ingredient_unchanged() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["비타민 K"]),
    )

    result = await resolver.resolve(
        question="비타민 K 영양제를 먹어도 되나요?",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.UNCHANGED
    assert result.corrections == []


@pytest.mark.asyncio
async def test_resolver_corrects_relation_expression_after_two_catalog_entities() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticTypedExpressionCatalog(
            [
                MedicationCatalogEntry(
                    canonical_name="와파린",
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.DRUG,
                    source=MedicationQueryEntitySource.RDBMS,
                ),
                MedicationCatalogEntry(
                    canonical_name="비타민 K",
                    entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                    kind=InteractionEntityKind.SUPPLEMENT,
                    source=MedicationQueryEntitySource.QDRANT,
                ),
            ]
        ),
    )

    result = await resolver.resolve(
        question="와파린이랑 비타민 K 머거도 대?",
    )

    assert result.status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
    assert result.resolved_question == "와파린이랑 비타민 K 먹어도 돼?"
    assert [entity.canonical_name for entity in result.entities] == [
        "와파린",
        "비타민 K",
    ]
    assert result.normalization_strategy.value == "RELATION_CUE"
    assert result.relation_resolution_status.value == "AUTO_CORRECTED"


@pytest.mark.asyncio
async def test_resolver_recognizes_controlled_supplement_names_without_db_rows() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["칼슘", "철분"]),
    )

    result = await resolver.resolve(
        question="칼슘과 철분을 같이 먹어도 되나요?",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.UNCHANGED


@pytest.mark.asyncio
async def test_resolver_requests_clarification_for_shared_product_prefix() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(
            ["마그네슘", "마그네정", "마그네캡슐"],
        ),
    )

    result = await resolver.resolve(
        question="마그 복용법 알려줘",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == (MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED)
    assert result.candidate_names == ["마그네슘", "마그네정", "마그네캡슐"]


@pytest.mark.asyncio
async def test_resolver_uses_longest_multiword_prefix_for_ingredient_family() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(
            [
                "비타민 A",
                "비타민 B1",
                "비타민 B2",
                "비타민 B12",
                "비타민 B12 500 다이렉트",
            ],
        ),
    )

    result = await resolver.resolve(question="비타민 B는 어떤 역할을 해?")

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == (MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED)
    assert result.candidate_names == [
        "비타민 B1",
        "비타민 B12",
        "비타민 B12 500 다이렉트",
        "비타민 B2",
    ]


@pytest.mark.asyncio
async def test_resolver_requests_clarification_for_tied_candidates() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["타이레놀", "타이레널"]),
    )

    result = await resolver.resolve(
        question="타이레늘 복용법 알려줘",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == (MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED)
    assert result.candidate_names == ["타이레널", "타이레놀"]


@pytest.mark.asyncio
async def test_resolver_does_not_auto_correct_short_ambiguous_name() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["철", "인"]),
    )

    result = await resolver.resolve(
        question="찰 영양제는 왜 먹나요?",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status != MedicationExpressionResolutionStatus.AUTO_CORRECTED


@pytest.mark.asyncio
async def test_resolver_separates_greeting_from_out_of_scope_question() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["타이레놀"]),
    )

    greeting = await resolver.resolve(question="안녕하세요")
    out_of_scope = await resolver.resolve(question="오늘 너무 배고파요")

    assert greeting.scope == MedicationQuestionScope.GREETING
    assert out_of_scope.scope == MedicationQuestionScope.OUT_OF_SCOPE


@pytest.mark.asyncio
async def test_resolver_does_not_correct_out_of_scope_word_into_product() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["배고파정"]),
    )

    result = await resolver.resolve(question="오늘 너무 배고파요")

    assert result.scope == MedicationQuestionScope.OUT_OF_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.UNRESOLVED


@pytest.mark.asyncio
async def test_resolver_does_not_correct_bare_general_word_into_product() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog(["배고파정"]),
    )

    result = await resolver.resolve(question="배고파요")

    assert result.scope == MedicationQuestionScope.OUT_OF_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.UNRESOLVED


@pytest.mark.asyncio
async def test_resolver_keeps_related_question_without_catalog_match_in_scope() -> None:
    resolver = RuleBasedMedicationQuestionResolver(
        catalog=StaticExpressionCatalog([]),
    )

    result = await resolver.resolve(
        question="처음 보는 약의 복용 시 주의사항을 알려줘",
    )

    assert result.scope == MedicationQuestionScope.IN_SCOPE
    assert result.status == MedicationExpressionResolutionStatus.UNRESOLVED


@pytest.mark.asyncio
async def test_resolver_reuses_normalized_catalog_without_mutating_source() -> None:
    catalog = StaticExpressionCatalog(["타이레놀"])
    resolver = RuleBasedMedicationQuestionResolver(catalog=catalog)

    await resolver.resolve(
        question="타이래놀 복용법 알려줘",
        additional_names=["마그네슘"],
    )
    await resolver.resolve(question="아세트아미노펜 복용법 알려줘")

    assert catalog.call_count == 1
    assert catalog.expressions == ["타이레놀"]
