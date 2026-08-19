import hashlib
import hmac

from passlib.context import CryptContext

from app.core import config

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

PASSWORD_FINGERPRINT_LENGTH = 16


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def password_fingerprint(hashed_password: str) -> str:
    """비밀번호 해시에서 파생한 짧은 지문.

    리프레시 토큰에 담아두고 갱신할 때 DB 값과 비교한다. 비밀번호가 바뀌면 지문이
    달라지므로 **이전에 발급된 리프레시 토큰이 기기와 무관하게 모두 무효**가 된다.
    JWT 는 서버에 저장하지 않아 개별 폐기가 안 되는데, 이 방식이면 상태 저장 없이
    같은 효과를 낸다(Django 의 세션 인증 해시와 같은 방식).

    해시 원문을 토큰에 그대로 노출하지 않도록 SECRET_KEY 로 HMAC 을 건다.
    """
    digest = hmac.new(config.SECRET_KEY.encode(), hashed_password.encode(), hashlib.sha256)
    return digest.hexdigest()[:PASSWORD_FINGERPRINT_LENGTH]
