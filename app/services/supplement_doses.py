from datetime import date, datetime, timedelta

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.supplement_doses import SupplementDoseRequest, SupplementDoseResponse
from app.models.enums import MealSlot, SupplementStatus
from app.models.supplement_nutrients import SupplementDose, UserSupplementNutrientSlot
from app.models.users import User
from app.repositories.user_supplement_nutrient_repository import UserSupplementNutrientRepository

SLOT_ORDER = {slot: index for index, slot in enumerate(MealSlot)}


class SupplementDoseService:
    @staticmethod
    def validate_date(dose_date: date) -> None:
        today = datetime.now(config.TIMEZONE).date()
        if not today - timedelta(days=365) <= dose_date <= today:
            raise HTTPException(status_code=422, detail="오늘까지 최근 366일의 복용 기록만 저장할 수 있어요.")

    async def list(self, user: User, dose_date: date) -> list[SupplementDoseResponse]:
        self.validate_date(dose_date)
        records = await SupplementDose.filter(registration__user_id=user.id, dose_date=dose_date)
        records.sort(key=lambda item: (SLOT_ORDER[item.slot], item.registration_id))
        return [
            SupplementDoseResponse(
                supplement_id=item.registration_id,
                date=item.dose_date,
                slot=item.slot.value.lower(),
                taken=True,
            )
            for item in records
        ]

    async def save(self, user: User, data: SupplementDoseRequest) -> SupplementDoseResponse:
        async with in_transaction() as connection:
            # Lock the registration so concurrent save/undo and registration edits serialize.
            registration = await UserSupplementNutrientRepository().get_owned_for_update(
                data.supplement_id,
                user.id,
                connection,
            )
            if registration is None:
                raise HTTPException(status_code=404, detail="영양제를 찾지 못했어요.")
            self.validate_date(data.date)
            slot = MealSlot(data.slot.upper())
            key = {"registration_id": registration.id, "dose_date": data.date, "slot": slot}
            if data.taken:
                has_slot = (
                    await UserSupplementNutrientSlot.filter(
                        user_suppl_nutrient_id=registration.id,
                        slot=slot,
                    )
                    .using_db(connection)
                    .exists()
                )
                if (
                    registration.status != SupplementStatus.ACTIVE
                    or data.date < registration.start_date
                    or (registration.end_date is not None and data.date > registration.end_date)
                    or not has_slot
                ):
                    raise HTTPException(status_code=422, detail="등록한 복용 기간과 시간대를 확인해주세요.")
                await SupplementDose.get_or_create(**key, using_db=connection)
            else:
                # A later registration edit/stop must not prevent undoing an existing record.
                await SupplementDose.filter(**key).using_db(connection).delete()
        return SupplementDoseResponse(**data.model_dump())
