import secrets
import string
from dataclasses import dataclass, field

from app.core.utils.security import hash_password

TEMPORARY_PASSWORD_LENGTH = 12

# validate_password 가 요구하는 네 종류. 각 종류에서 최소 1자씩 뽑아 정책을 항상 만족시킨다.
_SPECIAL_CHARACTERS = "!@#$%^&*"
_REQUIRED_GROUPS = (string.ascii_uppercase, string.ascii_lowercase, string.digits, _SPECIAL_CHARACTERS)
_ALPHABET = string.ascii_letters + string.digits + _SPECIAL_CHARACTERS


def _shuffled(characters: list[str]) -> str:
    """secrets 기반 Fisher-Yates. random 모듈을 섞어 쓰지 않으려고 직접 구현한다."""
    for index in range(len(characters) - 1, 0, -1):
        swap = secrets.randbelow(index + 1)
        characters[index], characters[swap] = characters[swap], characters[index]
    return "".join(characters)


def generate_temporary_password() -> str:
    """정책(대문자·소문자·숫자·특수문자 각 1개 이상, 8자 이상)을 항상 만족하는 임시 비밀번호.

    전체 알파벳에서 균일하게 뽑으면 12자 기준 약 36%가 어느 한 종류를 빠뜨린다
    (특수문자 누락 23%, 숫자 누락 15%). 서버가 자기 정책을 통과하지 못하는 값을
    발급하지 않도록, 종류별로 1자씩 확보한 뒤 나머지를 채우고 섞는다.
    """
    characters = [secrets.choice(group) for group in _REQUIRED_GROUPS]
    remaining = TEMPORARY_PASSWORD_LENGTH - len(characters)
    characters += [secrets.choice(_ALPHABET) for _ in range(remaining)]
    return _shuffled(characters)


@dataclass(frozen=True)
class TemporaryCredential:
    """새로 발급한 임시 비밀번호 한 건.

    평문은 메일 발송에만 쓰고 저장하지 않는다. repr 에서도 빼서 로그·예외 메시지에
    딸려 나가지 않게 한다. 호출부는 hashed_password 만 다루면 된다.
    """

    hashed_password: str
    _plaintext: str = field(repr=False)

    @property
    def plaintext_for_delivery(self) -> str:
        """암호화된 이메일 작업 payload를 만드는 짧은 구간에서만 평문을 제공한다."""
        return self._plaintext


def issue_temporary_password() -> TemporaryCredential:
    """임시 비밀번호를 만들어 해시와 함께 돌려준다.

    등록(REQ-ADMIN-008)과 재발송(REQ-ADMIN-003)이 같은 방식을 써야 하므로 한곳에 둔다.
    이메일 작업 등록은 호출부가 계정을 저장한 뒤 별도로 한다. 저장보다 먼저 등록하면
    저장이 실패했을 때 존재하지 않는 계정의 비밀번호 발송 작업이 남게 된다.
    """
    plaintext = generate_temporary_password()
    return TemporaryCredential(hashed_password=hash_password(plaintext), _plaintext=plaintext)
