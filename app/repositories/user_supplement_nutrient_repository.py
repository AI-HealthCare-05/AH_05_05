from tortoise.backends.base.client import BaseDBAsyncClient

from app.models.enums import MealSlot, SupplementStatus
from app.models.supplement_nutrients import (
    SupplementNutrient,
    UserSupplementNutrient,
    UserSupplementNutrientSlot,
)
from app.models.users import UserSettings


class UserSupplementNutrientRepository:
    async def get_product(self, product_id: int) -> SupplementNutrient | None:
        return await SupplementNutrient.get_or_none(id=product_id)

    async def get_owned(self, registration_id: int, user_id: int) -> UserSupplementNutrient | None:
        return await (
            UserSupplementNutrient.filter(id=registration_id, user_id=user_id)
            .prefetch_related("supplement_nutrient", "slots")
            .first()
        )

    async def get_owned_for_update(
        self,
        registration_id: int,
        user_id: int,
        connection: BaseDBAsyncClient,
    ) -> UserSupplementNutrient | None:
        return await (
            UserSupplementNutrient.filter(id=registration_id, user_id=user_id)
            .using_db(connection)
            .select_for_update()
            .first()
        )

    async def get_by_user_product_for_update(
        self,
        user_id: int,
        product_id: int,
        connection: BaseDBAsyncClient,
    ) -> UserSupplementNutrient | None:
        return await (
            UserSupplementNutrient.filter(user_id=user_id, supplement_nutrient_id=product_id)
            .using_db(connection)
            .select_for_update()
            .first()
        )

    async def list_owned(
        self,
        user_id: int,
        *,
        registration_status: SupplementStatus | None,
        offset: int,
        limit: int,
    ) -> tuple[list[UserSupplementNutrient], int]:
        query = UserSupplementNutrient.filter(user_id=user_id)
        if registration_status is not None:
            query = query.filter(status=registration_status)
        total = await query.count()
        items = await (
            query.order_by("status", "-start_date", "-id")
            .offset(offset)
            .limit(limit)
            .prefetch_related("supplement_nutrient", "slots")
        )
        return items, total

    async def get_or_create_settings(
        self,
        user_id: int,
        connection: BaseDBAsyncClient | None = None,
    ) -> UserSettings:
        settings, _ = await UserSettings.get_or_create(user_id=user_id, using_db=connection)
        return settings

    async def replace_slots(
        self,
        registration_id: int,
        slots: list[MealSlot],
        connection: BaseDBAsyncClient,
    ) -> None:
        await UserSupplementNutrientSlot.filter(user_suppl_nutrient_id=registration_id).using_db(connection).delete()
        await UserSupplementNutrientSlot.bulk_create(
            [UserSupplementNutrientSlot(user_suppl_nutrient_id=registration_id, slot=slot) for slot in slots],
            using_db=connection,
        )
