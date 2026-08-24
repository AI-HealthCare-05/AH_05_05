from datetime import date, datetime, time
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.dtos.supplement_nutrients import SupplementNutrientResponse
from app.models.enums import MealSlot, SupplementStatus


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
    dose_amount: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    dose_unit: str | None = Field(default=None, min_length=1, max_length=20)
    start_date: date | None = None
    end_date: date | None = None
    status: SupplementStatus | None = None
    slots: list[MealSlot] | None = Field(default=None, min_length=1, max_length=4)
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
    dose_amount: Decimal
    dose_unit: str
    start_date: date
    end_date: date | None
    status: SupplementStatus
    note: str | None
    created_at: datetime
    updated_at: datetime | None
    slots: list[SupplementSlotResponse]
    supplement: SupplementNutrientResponse


class UserSupplementNutrientListResponse(BaseModel):
    items: list[UserSupplementNutrientResponse]
    total: int
    offset: int
    limit: int
