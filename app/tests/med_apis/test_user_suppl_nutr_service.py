from datetime import date, time

import pytest
from fastapi import HTTPException
from tortoise.contrib.test import TestCase

from app.dtos.user_supplement_nutrients import (
    UserSupplementNutrientUpdateRequest,
    UserSupplementNutrientUpsertRequest,
)
from app.models.enums import AccountStatus, SupplementStatus
from app.models.supplement_nutrients import UserSupplementNutrient, UserSupplementNutrientSlot
from app.models.users import User, UserSettings
from app.tests.med_apis.helpers import create_supplement


async def create_user(email: str) -> User:
    return await User.create(
        email=email,
        hashed_password="hashed-password",
        status=AccountStatus.ACTIVE,
        name="영양제 서비스 사용자",
    )


def upsert_request(slots: list[str]) -> UserSupplementNutrientUpsertRequest:
    return UserSupplementNutrientUpsertRequest.model_validate(
        {
            "dose_amount": "1.000",
            "dose_unit": "정",
            "start_date": "2026-08-24",
            "slots": slots,
            "note": "식후 복용",
        }
    )


class TestUserSupplementNutrientService(TestCase):
    async def test_upsert_reuses_registration_replaces_slots_and_creates_settings(self) -> None:
        from app.services.user_supplement_nutrients import UserSupplementNutrientService

        user = await create_user("suppl-upsert@example.com")
        product = await create_supplement("SUPPL-001", "철분")
        service = UserSupplementNutrientService()

        first = await service.upsert(user, product.id, upsert_request(["MORNING", "EVENING"]))
        second = await service.upsert(user, product.id, upsert_request(["BEDTIME"]))

        assert first.id == second.id
        assert await UserSupplementNutrient.filter(user=user, supplement_nutrient=product).count() == 1
        assert await UserSupplementNutrientSlot.filter(user_suppl_nutrient_id=second.id).count() == 1
        assert [slot.slot.value for slot in second.slots] == ["BEDTIME"]
        assert [slot.time for slot in second.slots] == [time(22, 0)]
        assert second.status is SupplementStatus.ACTIVE
        assert await UserSettings.filter(user=user).count() == 1

    async def test_update_validates_merged_date_range_without_changing_database(self) -> None:
        from app.services.user_supplement_nutrients import UserSupplementNutrientService

        user = await create_user("suppl-update@example.com")
        product = await create_supplement("SUPPL-002", "비타민 D")
        service = UserSupplementNutrientService()
        created = await service.upsert(user, product.id, upsert_request(["MORNING"]))
        registration = await UserSupplementNutrient.get(id=created.id)
        registration.end_date = date(2026, 8, 24)
        await registration.save(update_fields=["end_date"])

        with pytest.raises(HTTPException) as exc_info:
            await service.update(
                user,
                created.id,
                UserSupplementNutrientUpdateRequest(start_date=date(2026, 8, 25)),
            )

        assert exc_info.value.status_code == 422
        stored = await UserSupplementNutrient.get(id=created.id)
        assert stored.start_date == date(2026, 8, 24)
        assert stored.end_date == date(2026, 8, 24)

    async def test_complete_is_idempotent_and_owner_scoped(self) -> None:
        from app.services.user_supplement_nutrients import UserSupplementNutrientService

        owner = await create_user("suppl-owner@example.com")
        other = await create_user("suppl-other@example.com")
        product = await create_supplement("SUPPL-003", "오메가3")
        service = UserSupplementNutrientService()
        created = await service.upsert(owner, product.id, upsert_request(["LUNCH"]))

        await service.complete(owner, created.id)
        first_end_date = (await UserSupplementNutrient.get(id=created.id)).end_date
        await service.complete(owner, created.id)

        stored = await UserSupplementNutrient.get(id=created.id)
        assert stored.status is SupplementStatus.COMPLETED
        assert stored.end_date == first_end_date
        with pytest.raises(HTTPException) as exc_info:
            await service.get(other, created.id)
        assert exc_info.value.status_code == 404
