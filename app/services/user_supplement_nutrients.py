from datetime import datetime, time, timedelta

from fastapi import HTTPException, status
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.supplement_nutrients import SupplementNutrientResponse
from app.dtos.user_supplement_nutrients import (
    SupplementSlotResponse,
    UserSupplementNutrientListResponse,
    UserSupplementNutrientResponse,
    UserSupplementNutrientUpdateRequest,
    UserSupplementNutrientUpsertRequest,
)
from app.models.enums import MealSlot, SupplementStatus
from app.models.supplement_nutrients import UserSupplementNutrient
from app.models.users import User, UserSettings
from app.repositories.user_supplement_nutrient_repository import UserSupplementNutrientRepository

SLOT_ORDER = {
    MealSlot.MORNING: 0,
    MealSlot.LUNCH: 1,
    MealSlot.EVENING: 2,
    MealSlot.BEDTIME: 3,
}

SLOT_TIME_FIELDS = {
    MealSlot.MORNING: "morning_medication_time",
    MealSlot.LUNCH: "lunch_medication_time",
    MealSlot.EVENING: "evening_medication_time",
    MealSlot.BEDTIME: "bedtime_medication_time",
}


def normalize_mysql_time(value: time | timedelta) -> time:
    """Convert MySQL TIME values returned by asyncmy into API time values."""
    if isinstance(value, time):
        return value
    seconds = int(value.total_seconds()) % (24 * 60 * 60)
    hour, remainder = divmod(seconds, 60 * 60)
    minute, second = divmod(remainder, 60)
    return time(hour=hour, minute=minute, second=second)


class UserSupplementNutrientService:
    def __init__(self, repository: UserSupplementNutrientRepository | None = None):
        self.repository = repository or UserSupplementNutrientRepository()

    async def upsert(
        self,
        user: User,
        supplement_nutrient_id: int,
        data: UserSupplementNutrientUpsertRequest,
    ) -> UserSupplementNutrientResponse:
        product = await self.repository.get_product(supplement_nutrient_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplement nutrient not found.")

        try:
            registration_id = await self._write_upsert(user.id, supplement_nutrient_id, data)
        except IntegrityError:
            registration_id = await self._write_upsert(user.id, supplement_nutrient_id, data)
        return await self.get(user, registration_id)

    async def _write_upsert(
        self,
        user_id: int,
        supplement_nutrient_id: int,
        data: UserSupplementNutrientUpsertRequest,
    ) -> int:
        async with in_transaction() as connection:
            await self.repository.get_or_create_settings(user_id, connection)
            registration = await self.repository.get_by_user_product_for_update(
                user_id,
                supplement_nutrient_id,
                connection,
            )
            values = data.model_dump(exclude={"slots"})
            values["status"] = SupplementStatus.ACTIVE
            if registration is None:
                registration = await UserSupplementNutrient.create(
                    user_id=user_id,
                    supplement_nutrient_id=supplement_nutrient_id,
                    using_db=connection,
                    **values,
                )
            else:
                for field_name, value in values.items():
                    setattr(registration, field_name, value)
                registration.updated_at = datetime.now(config.TIMEZONE)
                await registration.save(
                    using_db=connection,
                    update_fields=[*values, "updated_at"],
                )
            await self.repository.replace_slots(registration.id, data.slots, connection)
            return registration.id

    async def list(
        self,
        user: User,
        *,
        registration_status: SupplementStatus | None,
        offset: int,
        limit: int,
    ) -> UserSupplementNutrientListResponse:
        registrations, total = await self.repository.list_owned(
            user.id,
            registration_status=registration_status,
            offset=offset,
            limit=limit,
        )
        settings = await self.repository.get_or_create_settings(user.id)
        return UserSupplementNutrientListResponse(
            items=[self._to_response(registration, settings) for registration in registrations],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get(self, user: User, registration_id: int) -> UserSupplementNutrientResponse:
        registration = await self.repository.get_owned(registration_id, user.id)
        if registration is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User supplement nutrient not found.")
        settings = await self.repository.get_or_create_settings(user.id)
        return self._to_response(registration, settings)

    async def update(
        self,
        user: User,
        registration_id: int,
        data: UserSupplementNutrientUpdateRequest,
    ) -> UserSupplementNutrientResponse:
        async with in_transaction() as connection:
            registration = await self.repository.get_owned_for_update(registration_id, user.id, connection)
            if registration is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User supplement nutrient not found.",
                )
            updates = data.model_dump(exclude_unset=True)
            slots = updates.pop("slots", None)
            merged_start_date = updates.get("start_date", registration.start_date)
            merged_end_date = updates.get("end_date", registration.end_date)
            if updates.get("status") == SupplementStatus.COMPLETED and "end_date" not in updates:
                merged_end_date = datetime.now(config.TIMEZONE).date()
                updates["end_date"] = merged_end_date
            if merged_end_date is not None and merged_end_date < merged_start_date:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="end_date must be on or after start_date.",
                )
            if updates:
                for field_name, value in updates.items():
                    setattr(registration, field_name, value)
                registration.updated_at = datetime.now(config.TIMEZONE)
                await registration.save(
                    using_db=connection,
                    update_fields=[*updates, "updated_at"],
                )
            if slots is not None:
                await self.repository.replace_slots(registration.id, slots, connection)
        return await self.get(user, registration_id)

    async def complete(self, user: User, registration_id: int) -> None:
        async with in_transaction() as connection:
            registration = await self.repository.get_owned_for_update(registration_id, user.id, connection)
            if registration is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User supplement nutrient not found.",
                )
            if registration.status == SupplementStatus.COMPLETED:
                return
            now = datetime.now(config.TIMEZONE)
            registration.status = SupplementStatus.COMPLETED
            registration.end_date = now.date()
            registration.updated_at = now
            await registration.save(
                using_db=connection,
                update_fields=["status", "end_date", "updated_at"],
            )

    @staticmethod
    def _to_response(
        registration: UserSupplementNutrient,
        settings: UserSettings,
    ) -> UserSupplementNutrientResponse:
        slots = sorted(registration.slots, key=lambda item: SLOT_ORDER[item.slot])
        return UserSupplementNutrientResponse(
            id=registration.id,
            dose_amount=registration.dose_amount,
            dose_unit=registration.dose_unit,
            start_date=registration.start_date,
            end_date=registration.end_date,
            status=registration.status,
            note=registration.note,
            created_at=registration.created_at,
            updated_at=registration.updated_at,
            slots=[
                SupplementSlotResponse(
                    slot=slot.slot,
                    time=normalize_mysql_time(getattr(settings, SLOT_TIME_FIELDS[slot.slot])),
                )
                for slot in slots
            ],
            supplement=SupplementNutrientResponse.model_validate(registration.supplement_nutrient),
        )
