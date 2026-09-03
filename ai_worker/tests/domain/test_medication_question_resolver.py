import pytest

from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.schemas.medication_search import (
    MedicationExpressionResolutionStatus,
    MedicationQuestionScope,
)


class StaticExpressionCatalog:
    def __init__(self, expressions: list[str]) -> None:
        self.expressions = expressions
        self.call_count = 0

    async def list_expressions(self) -> list[str]:
        self.call_count += 1
        return self.expressions


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
