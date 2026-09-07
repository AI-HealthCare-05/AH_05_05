import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pydantic import BaseModel, SecretStr, ValidationError

from app.models.enums import EmailVerificationPurpose


class EmailVerificationConfigurationError(RuntimeError):
    """이메일 인증 비밀키 설정이 없거나 올바르지 않다."""


class InvalidEmailVerificationTokenError(ValueError):
    """이메일 인증 토큰이 변조됐거나 만료됐다."""


class EmailVerificationTokenClaims(BaseModel):
    verification_id: int
    email: str
    purpose: EmailVerificationPurpose


def _secret_value(secret: str | SecretStr | None) -> str:
    value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    if not value:
        raise EmailVerificationConfigurationError("EMAIL_VERIFICATION_SECRET가 설정되지 않았습니다.")
    return value


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def digest_verification_code(
    *,
    secret: str | SecretStr | None,
    verification_id: int,
    email: str,
    purpose: EmailVerificationPurpose,
    code: str,
) -> str:
    message = f"{verification_id}:{email.casefold()}:{purpose.value}:{code}".encode()
    return hmac.new(_secret_value(secret).encode(), message, hashlib.sha256).hexdigest()


class EmailVerificationTokenCodec:
    def __init__(self, secret: str | SecretStr | None, *, algorithm: str, ttl_seconds: int) -> None:
        self._secret = _secret_value(secret)
        self._algorithm = algorithm
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        verification_id: int,
        email: str,
        purpose: EmailVerificationPurpose,
    ) -> str:
        issued_at = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": "email-verification",
                "verification_id": verification_id,
                "email": email.casefold(),
                "purpose": purpose.value,
                "iat": issued_at,
                "exp": issued_at + timedelta(seconds=self._ttl_seconds),
            },
            self._secret,
            algorithm=self._algorithm,
        )

    def verify(self, token: str) -> EmailVerificationTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["sub", "verification_id", "email", "purpose", "iat", "exp"]},
            )
            if payload["sub"] != "email-verification":
                raise InvalidEmailVerificationTokenError("유효하지 않은 이메일 인증 토큰입니다.")
            return EmailVerificationTokenClaims.model_validate(payload)
        except InvalidEmailVerificationTokenError:
            raise
        except (jwt.PyJWTError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise InvalidEmailVerificationTokenError("유효하지 않은 이메일 인증 토큰입니다.") from exc
