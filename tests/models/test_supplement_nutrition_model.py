from decimal import Decimal
from importlib import import_module

import pytest
from tortoise import Tortoise, fields


def load_models():
    try:
        enums = import_module("app.models.enums")
        supplements = import_module("app.models.supplement_nutrients")
    except ModuleNotFoundError as exc:
        pytest.fail(f"supplement nutrition model module is missing: {exc.name}")

    Tortoise.init_models(
        (
            "app.models.users",
            "app.models.admins",
            "app.models.supplement_nutrients",
        ),
        "models",
    )
    return enums, supplements


def test_supplement_nutrient_matches_source_schema() -> None:
    _, supplements = load_models()
    model = supplements.SupplementNutrient

    assert model._meta.db_table == "supplement_nutrients"
    assert model._meta.fields_map["food_code"].max_length == 20
    assert model._meta.fields_map["food_code"].unique is True
    assert model._meta.fields_map["name"].max_length == 100
    assert model._meta.fields_map["protein_g"].max_digits == 5
    assert model._meta.fields_map["protein_g"].decimal_places == 2
    assert model._meta.fields_map["water_g"].null is True
    assert model._meta.fields_map["energy_kcal"].null is False


def test_user_supplement_relationships_and_constraints() -> None:
    enums, supplements = load_models()
    registration = supplements.UserSupplementNutrient
    slot = supplements.UserSupplementNutrientSlot

    assert {status.value for status in enums.SupplementStatus} == {
        "ACTIVE",
        "PAUSED",
        "COMPLETED",
    }
    assert registration._meta.db_table == "user_suppl_nutrient"
    assert registration._meta.unique_together == (("user", "supplement_nutrient"),)
    assert registration._meta.fields_map["user"].on_delete == fields.CASCADE
    assert registration._meta.fields_map["supplement_nutrient"].on_delete == fields.RESTRICT
    assert registration._meta.fields_map["status"].default is enums.SupplementStatus.ACTIVE
    assert registration._meta.fields_map["dose_amount"].validators[0].min_value == Decimal("0.001")
    assert slot._meta.db_table == "user_suppl_nutrient_slots"
    assert slot._meta.unique_together == (("user_suppl_nutrient", "slot"),)
    assert slot._meta.fields_map["slot"].enum_type is enums.MealSlot
    assert slot._meta.fields_map["user_suppl_nutrient"].on_delete == fields.CASCADE


def test_supplement_ranking_display_relationships_and_constraints() -> None:
    _, supplements = load_models()
    display = supplements.DisplaySupplementNutrientRank
    item = supplements.SupplementNutrientRankItem

    assert display._meta.db_table == "display_suppl_nutr_rank"
    assert display._meta.fields_map["title"].max_length == 100
    assert display._meta.fields_map["is_enabled"].default is False
    assert display._meta.fields_map["created_by_admin"].on_delete == fields.SET_NULL
    assert item._meta.db_table == "suppl_nutr_rank_item"
    assert item._meta.unique_together == (
        ("display", "supplement_nutrient"),
        ("display", "rank_no"),
    )
    assert item._meta.fields_map["display"].on_delete == fields.CASCADE
    assert item._meta.fields_map["supplement_nutrient"].on_delete == fields.RESTRICT
    assert item._meta.fields_map["rank_no"].validators[0].min_value == 1
