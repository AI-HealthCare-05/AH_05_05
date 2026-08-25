from decimal import Decimal

from scripts.import_nutrient_standards import DEFAULT_PATH, EXPECTED_HEADERS, parse_csv


def test_generated_csv_matches_wide_schema_and_preserves_nulls() -> None:
    records = parse_csv(DEFAULT_PATH)

    assert len(EXPECTED_HEADERS) == 47
    assert len(records) == 24
    assert records[0]["grp"] == "영아"
    assert records[0]["age"] == "0-5개월"
    assert records[0]["carb_g_rni"] is None
    assert records[0]["carb_g_ai"] == Decimal("55")


def test_source_comma_values_are_normalized_to_numeric_values() -> None:
    records = parse_csv(DEFAULT_PATH)
    by_target = {(record["grp"], record["age"]): record for record in records}

    assert by_target[("남자", "19-29세")]["phosphorus_mg_rni"] == Decimal("650")
    assert by_target[("여자", "6-8세")]["vitamin_c_mg_ul"] == Decimal("750")
    assert by_target[("임신부", None)]["calcium_mg_rni"] == Decimal("0")
