from decimal import Decimal

from pydantic import BaseModel

from app.dtos.base import BaseSerializerModel


class SupplementNutrientResponse(BaseSerializerModel):
    id: int
    food_code: str
    name: str
    basis_qty: str
    energy_kcal: int
    water_g: Decimal | None
    protein_g: Decimal
    fat_g: Decimal | None
    ash_g: Decimal | None
    carb_g: Decimal
    sugar_g: Decimal | None
    fiber_g: Decimal | None
    calcium_mg: int | None
    iron_mg: Decimal | None
    phosphorus_mg: int | None
    potassium_mg: int | None
    sodium_mg: int | None
    vitamin_a_ug_rae: int | None
    retinol_ug: int | None
    beta_carotene_ug: int | None
    thiamine_mg: Decimal | None
    riboflavin_mg: Decimal | None
    niacin_mg: Decimal | None
    vitamin_c_mg: Decimal | None
    vitamin_d_ug: Decimal | None
    cholesterol_mg: Decimal | None
    sat_fat_g: Decimal | None
    trans_fat_g: Decimal | None
    serving_desc: str
    serving_size: str
    daily_freq: str
    target: str | None


class SupplementNutrientListResponse(BaseModel):
    items: list[SupplementNutrientResponse]
    total: int
    offset: int
    limit: int


class PopularSupplementNutrientResponse(BaseModel):
    id: int
    name: str
