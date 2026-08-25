from decimal import Decimal

from pydantic import BaseModel

from app.dtos.base import BaseSerializerModel


class NutrientStandardResponse(BaseSerializerModel):
    id: int
    grp: str
    age: str | None
    carb_g_rni: Decimal | None
    carb_g_ai: Decimal | None
    carb_g_ul: Decimal | None
    protein_g_rni: Decimal | None
    protein_g_ai: Decimal | None
    protein_g_ul: Decimal | None
    fat_g_rni: Decimal | None
    fat_g_ai: Decimal | None
    fat_g_ul: Decimal | None
    fiber_g_rni: Decimal | None
    fiber_g_ai: Decimal | None
    fiber_g_ul: Decimal | None
    calcium_mg_rni: Decimal | None
    calcium_mg_ai: Decimal | None
    calcium_mg_ul: Decimal | None
    iron_mg_rni: Decimal | None
    iron_mg_ai: Decimal | None
    iron_mg_ul: Decimal | None
    phosphorus_mg_rni: Decimal | None
    phosphorus_mg_ai: Decimal | None
    phosphorus_mg_ul: Decimal | None
    potassium_mg_rni: Decimal | None
    potassium_mg_ai: Decimal | None
    potassium_mg_ul: Decimal | None
    sodium_mg_rni: Decimal | None
    sodium_mg_ai: Decimal | None
    sodium_mg_ul: Decimal | None
    vitamin_a_ug_rae_rni: Decimal | None
    vitamin_a_ug_rae_ai: Decimal | None
    vitamin_a_ug_rae_ul: Decimal | None
    thiamine_mg_rni: Decimal | None
    thiamine_mg_ai: Decimal | None
    thiamine_mg_ul: Decimal | None
    riboflavin_mg_rni: Decimal | None
    riboflavin_mg_ai: Decimal | None
    riboflavin_mg_ul: Decimal | None
    niacin_mg_rni: Decimal | None
    niacin_mg_ai: Decimal | None
    niacin_mg_ul: Decimal | None
    vitamin_c_mg_rni: Decimal | None
    vitamin_c_mg_ai: Decimal | None
    vitamin_c_mg_ul: Decimal | None
    vitamin_d_ug_rni: Decimal | None
    vitamin_d_ug_ai: Decimal | None
    vitamin_d_ug_ul: Decimal | None


class NutrientStandardListResponse(BaseModel):
    items: list[NutrientStandardResponse]
    total: int
    offset: int
    limit: int
