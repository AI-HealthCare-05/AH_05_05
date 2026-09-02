from tortoise.functions import Count

from app.models.enums import AccountStatus
from app.models.supplement_nutrients import SupplementReviewReport, UserSupplementNutrient


class SupplementReviewRepository:
    async def list_hidden_registration_ids(self) -> list[int]:
        rows = (
            await SupplementReviewReport.all()
            .annotate(report_count=Count("id"))
            .group_by("registration_id")
            .filter(report_count__gte=3)
            .values_list("registration_id", flat=True)
        )
        return list(rows)

    async def list_withdrawn_owner_registration_ids(self) -> list[int]:
        rows = await UserSupplementNutrient.filter(user__status=AccountStatus.WITHDRAWN).values_list("id", flat=True)
        return list(rows)
