"""Contract tests for the declarative v11 lifestyle-guidance registry."""

import copy

import pytest

from ai_worker.reports.v11_lifestyle_guidance import (
    build_lifestyle_guidance_cards,
    load_lifestyle_guidance_registry,
)
from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportDataAvailability,
    IntakeReportDraft,
    IntakeReportExecutiveSummary,
    IntakeReportNutrientTotal,
)


def _draft_for(nutrient_name: str) -> IntakeReportDraft:
    return IntakeReportDraft(
        data_availability=IntakeReportDataAvailability(),
        executive_summary=IntakeReportExecutiveSummary(summary="검토했습니다."),
        nutrient_totals=[
            IntakeReportNutrientTotal(
                nutrient_name=nutrient_name,
                daily_total="1 mg",
                calculation_status="LABEL_SCHEDULE",
                amount="1",
                unit="mg",
                reference_value="2",
                reference_kind="RNI",
            )
        ],
        chart_data=IntakeReportChartData(),
        deterministic_markdown="# 보고서",
    )


def _synthetic_registry_data() -> dict[str, object]:
    return {
        "food_action": "테스트 식품 안내입니다.",
        "food_category": "테스트 식품",
        "timing_category": "테스트 시점",
        "foods": [
            {
                "nutrient_name": "테스트 영양소",
                "expected_units": ["mg"],
                "source": {
                    "id": "source:test-nutrient",
                    "title": "Synthetic source",
                    "organization": "Test organization",
                    "url": "https://example.test/source",
                    "evidence_level": "PUBLIC_GUIDE",
                },
                "title": "테스트 영양소 식품",
                "summary": "테스트용 비임상 사실입니다.",
                "card_id": "food:test-nutrient",
            }
        ],
        "timings": [],
    }


def test_default_registry_contains_the_reviewed_four_food_and_two_timing_entries() -> None:
    registry = load_lifestyle_guidance_registry()

    assert [spec.card_id for spec in registry.foods] == [
        "food:calcium",
        "food:iron",
        "food:vitamin-c",
        "food:vitamin-d",
    ]
    assert [spec.card_id for spec in registry.timings] == ["timing:vitamin-d", "timing:calcium"]


def test_injected_registry_entry_generates_a_card_without_a_nutrient_code_branch() -> None:
    registry = load_lifestyle_guidance_registry(_synthetic_registry_data())

    cards, sources = build_lifestyle_guidance_cards(_draft_for("테스트 영양소"), registry=registry)

    assert [card.id for card in cards] == ["food:test-nutrient"]
    assert cards[0].summary.endswith("테스트용 비임상 사실입니다.")
    assert cards[0].source_ids == ["source:test-nutrient"]
    assert [source.url for source in sources] == ["https://example.test/source"]


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda data: data["foods"].append(copy.deepcopy(data["foods"][0])),
            "duplicate card_id",
        ),
        (
            lambda data: data["foods"][0]["source"].pop("url"),
            "source.url",
        ),
        (
            lambda data: data["foods"][0]["source"].__setitem__("url", "ftp://example.test/source"),
            "source.url",
        ),
    ],
)
def test_registry_loader_fails_closed_for_duplicate_or_invalid_source_data(mutate, error: str) -> None:
    data = _synthetic_registry_data()
    mutate(data)

    with pytest.raises(ValueError, match=error):
        load_lifestyle_guidance_registry(data)


def test_unknown_nutrient_has_no_fallback_when_not_present_in_registry() -> None:
    registry = load_lifestyle_guidance_registry(_synthetic_registry_data())

    cards, sources = build_lifestyle_guidance_cards(_draft_for("등록되지 않은 영양소"), registry=registry)

    assert cards == []
    assert sources == []
