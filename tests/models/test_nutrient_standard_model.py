from tortoise import fields

from app.models.supplement_nutrients import NutrientStandard

NUTRIENT_PREFIXES = (
    "carb_g",
    "protein_g",
    "fat_g",
    "fiber_g",
    "calcium_mg",
    "iron_mg",
    "phosphorus_mg",
    "potassium_mg",
    "sodium_mg",
    "vitamin_a_ug_rae",
    "thiamine_mg",
    "riboflavin_mg",
    "niacin_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
)


def test_nutrient_standard_matches_excel_wide_schema() -> None:
    assert NutrientStandard._meta.db_table == "nutrient_standard"
    assert NutrientStandard._meta.indexes == (("grp", "age"),)

    fields_map = NutrientStandard._meta.fields_map
    assert fields_map["grp"].max_length == 10
    assert fields_map["age"].max_length == 20
    assert fields_map["age"].null is True

    for prefix in NUTRIENT_PREFIXES:
        for standard_type in ("rni", "ai", "ul"):
            field = fields_map[f"{prefix}_{standard_type}"]
            assert isinstance(field, fields.DecimalField)
            assert field.null is True
