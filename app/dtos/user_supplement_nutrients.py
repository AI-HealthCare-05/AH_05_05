from datetime import date, datetime, time
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.dtos.supplement_nutrients import SupplementNutrientResponse
from app.models.enums import MealSlot, SupplementStatus


class ManualSupplementNutrientCreateRequest(BaseModel):
    custom_name: str = Field(min_length=1, max_length=255)
    dose_amount: Decimal = Field(gt=0, max_digits=8, decimal_places=3)
    dose_unit: str = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date | None = None
    slots: list[MealSlot] = Field(min_length=1, max_length=4)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("custom_name", "dose_unit", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("slots")
    @classmethod
    def reject_duplicate_slots(cls, value: list[MealSlot]) -> list[MealSlot]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate supplement slots are not allowed.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class UserSupplementNutrientUpsertRequest(BaseModel):
    dose_amount: Decimal = Field(gt=0, max_digits=8, decimal_places=3)
    dose_unit: str = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date | None = None
    slots: list[MealSlot] = Field(min_length=1, max_length=4)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("dose_unit", mode="before")
    @classmethod
    def normalize_dose_unit(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("slots")
    @classmethod
    def reject_duplicate_slots(cls, value: list[MealSlot]) -> list[MealSlot]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate supplement slots are not allowed.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class UserSupplementNutrientUpdateRequest(BaseModel):
    # 전 필드가 선택이라 모르는 키를 무시하면 아무것도 안 바뀌고 성공 응답이 나간다.
    model_config = ConfigDict(extra="forbid")

    dose_amount: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    dose_unit: str | None = Field(default=None, min_length=1, max_length=20)
    start_date: date | None = None
    end_date: date | None = None
    status: SupplementStatus | None = None
    slots: list[MealSlot] | None = Field(default=None, min_length=1, max_length=4)
    note: str | None = Field(default=None, max_length=500)
    score: int | None = Field(default=None, ge=1, le=5)

    @field_validator("dose_unit", mode="before")
    @classmethod
    def normalize_dose_unit(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("slots")
    @classmethod
    def reject_duplicate_slots(cls, value: list[MealSlot] | None) -> list[MealSlot] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Duplicate supplement slots are not allowed.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class SupplementSlotResponse(BaseModel):
    slot: MealSlot
    time: time


class UserSupplementNutrientResponse(BaseModel):
    id: int
    custom_name: str | None
    dose_amount: Decimal
    dose_unit: str
    start_date: date
    end_date: date | None
    status: SupplementStatus
    note: str | None
    score: int | None
    created_at: datetime
    updated_at: datetime | None
    slots: list[SupplementSlotResponse]
    supplement: SupplementNutrientResponse | None


class NutrientStandardValues(BaseModel):
    rni: Decimal | None
    ai: Decimal | None
    ul: Decimal | None


class UserNutrientStandardResponse(BaseModel):
    grp: str
    age: str | None
    protein_g: NutrientStandardValues
    carb_g: NutrientStandardValues
    fat_g: NutrientStandardValues
    fiber_g: NutrientStandardValues
    calcium_mg: NutrientStandardValues
    iron_mg: NutrientStandardValues
    phosphorus_mg: NutrientStandardValues
    potassium_mg: NutrientStandardValues
    sodium_mg: NutrientStandardValues
    vitamin_a_ug_rae: NutrientStandardValues
    thiamine_mg: NutrientStandardValues
    riboflavin_mg: NutrientStandardValues
    niacin_mg: NutrientStandardValues
    vitamin_c_mg: NutrientStandardValues
    vitamin_d_ug: NutrientStandardValues


class UserSupplementNutrientListResponse(BaseModel):
    items: list[UserSupplementNutrientResponse]
    total: int
    offset: int
    limit: int
    nutrient_standard: UserNutrientStandardResponse | None = None
