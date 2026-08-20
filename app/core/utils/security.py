import secrets

from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

# admin.session_salt 컬럼 길이와 맞춘다. token_hex(16) 은 32자를 만든다.
SESSION_SALT_BYTES = 16


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def generate_session_salt() -> str:
    """세션 무효화용 난수를 만든다.

    admin.session_salt 에 저장하고 리프레시 토큰의 sid 클레임에 담는다. 갱신할 때
    둘을 대조하므로, 이 값을 새로 발급하면 **이전에 나간 리프레시 토큰이 기기와
    무관하게 모두 무효**가 된다. JWT 는 서버에 저장하지 않아 개별 폐기가 안 되는데,
    이 방식이면 Redis 같은 저장소 없이 같은 효과를 낸다.

    비밀번호 해시에서 값을 파생하지 않고 독립된 난수를 쓰는 이유는, 비밀번호 변경
    외에 정지·역할 변경 같은 사유로도 세션을 끊어야 하기 때문이다.
    """
    return secrets.token_hex(SESSION_SALT_BYTES)
