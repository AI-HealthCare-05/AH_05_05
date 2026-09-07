from datetime import datetime

from tortoise.backends.base.client import BaseDBAsyncClient

from app.models.email_verifications import EmailVerification
from app.models.enums import EmailVerificationPurpose


class EmailVerificationRepository:
    async def get_latest(
        self,
        *,
        email: str,
        purpose: EmailVerificationPurpose,
        using_db: BaseDBAsyncClient | None = None,
    ) -> EmailVerification | None:
        query = EmailVerification.filter(email=email, purpose=purpose)
        if using_db is not None:
            query = query.using_db(using_db)
        return await query.order_by("-created_at", "-id").first()

    async def get_for_update(
        self,
        verification_id: int,
        *,
        using_db: BaseDBAsyncClient,
    ) -> EmailVerification | None:
        return await EmailVerification.filter(id=verification_id).using_db(using_db).select_for_update().first()

    async def expire_open(
        self,
        *,
        email: str,
        purpose: EmailVerificationPurpose,
        now: datetime,
        using_db: BaseDBAsyncClient,
    ) -> int:
        return await (
            EmailVerification.filter(email=email, purpose=purpose, consumed_at=None)
            .using_db(using_db)
            .update(expires_at=now, updated_at=now)
        )
