"""Short-lived, user-bound snapshots for intake report email delivery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.core import config
from app.models.email_verifications import EmailVerification
from app.models.enums import AccountStatus, EmailVerificationPurpose
from app.models.users import User

INTAKE_REPORT_EMAIL_TOKEN_TTL_SECONDS = 60 * 60
# Payload accepts 200k Unicode characters. Fernet and base64 expansion can make a
# Korean-only report roughly four times larger on the wire.
MAX_INTAKE_REPORT_EMAIL_TOKEN_LENGTH = 900_000
MAX_INTAKE_REPORT_MARKDOWN_LENGTH = 200_000
_PURPOSE = "intake-report-email-v1"


class IntakeReportEmailTokenError(ValueError):
    """The client did not present a current, valid report-email snapshot."""


class IntakeReportEmailNotVerifiedError(PermissionError):
    """The account email has not completed signup verification."""


@dataclass(frozen=True)
class IntakeReportEmailSnapshot:
    user_id: int
    recipient_email: str
    report_id: str
    report_markdown: str


class IntakeReportEmailService:
    """Creates and consumes encrypted report snapshots without accepting email content from clients."""

    def __init__(self, *, encryption_key: str | SecretStr | None = None) -> None:
        self._encryption_key = encryption_key if encryption_key is not None else config.EMAIL_PAYLOAD_ENCRYPTION_KEY

    def create_snapshot_token(self, *, user: User, report_markdown: str) -> str | None:
        """Return None when email encryption is intentionally unavailable.

        Report generation must remain usable in environments that have not configured email.
        """
        if not report_markdown or len(report_markdown) > MAX_INTAKE_REPORT_MARKDOWN_LENGTH:
            return None
        try:
            fernet = self._fernet()
        except IntakeReportEmailTokenError:
            return None
        payload = {
            "purpose": _PURPOSE,
            "userId": user.id,
            "email": self._normalized_email(user.email),
            "reportId": str(uuid4()),
            "reportMarkdown": report_markdown,
        }
        return fernet.encrypt(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")

    def consume_snapshot_token(self, *, token: str, user: User) -> IntakeReportEmailSnapshot:
        if len(token) > MAX_INTAKE_REPORT_EMAIL_TOKEN_LENGTH:
            raise IntakeReportEmailTokenError("보고서 발송 요청이 유효하지 않습니다.")
        try:
            serialized = self._fernet().decrypt(
                token.encode("ascii"),
                ttl=INTAKE_REPORT_EMAIL_TOKEN_TTL_SECONDS,
            )
            payload = json.loads(serialized)
            if not isinstance(payload, dict):
                raise ValueError
            snapshot = IntakeReportEmailSnapshot(
                user_id=int(payload["userId"]),
                recipient_email=str(payload["email"]),
                report_id=str(payload["reportId"]),
                report_markdown=str(payload["reportMarkdown"]),
            )
        except (InvalidToken, UnicodeEncodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise IntakeReportEmailTokenError("보고서 발송 요청이 유효하지 않습니다.") from exc

        if (
            payload.get("purpose") != _PURPOSE
            or snapshot.user_id != user.id
            or snapshot.recipient_email != self._normalized_email(user.email)
            or not snapshot.report_id
            or not snapshot.report_markdown
        ):
            raise IntakeReportEmailTokenError("보고서 발송 요청이 유효하지 않습니다.")
        return snapshot

    async def require_verified_recipient(self, *, user: User) -> str:
        recipient_email = self._normalized_email(user.email)
        if user.status is not AccountStatus.ACTIVE or not await EmailVerification.filter(
            email=recipient_email,
            purpose=EmailVerificationPurpose.SIGNUP,
        ).exclude(verified_at=None).exists():
            raise IntakeReportEmailNotVerifiedError("이메일 인증을 완료한 계정에서만 보고서를 보낼 수 있습니다.")
        return recipient_email

    def _fernet(self) -> Fernet:
        key = self._encryption_key
        if isinstance(key, SecretStr):
            key = key.get_secret_value()
        if not key:
            raise IntakeReportEmailTokenError("보고서 이메일 기능을 사용할 수 없습니다.")
        try:
            return Fernet(key.encode("ascii"))
        except (UnicodeEncodeError, ValueError) as exc:
            raise IntakeReportEmailTokenError("보고서 이메일 기능을 사용할 수 없습니다.") from exc

    @staticmethod
    def _normalized_email(email: str) -> str:
        return email.casefold()
