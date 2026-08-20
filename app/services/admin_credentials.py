import secrets
import string
from dataclasses import dataclass, field

from app.core.utils.security import hash_password
from app.services.admin_email import send_temporary_password

TEMPORARY_PASSWORD_LENGTH = 12
_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


@dataclass(frozen=True)
class TemporaryCredential:
    """새로 발급한 임시 비밀번호 한 건.

    평문은 메일 발송에만 쓰고 저장하지 않는다. repr 에서도 빼서 로그·예외 메시지에
    딸려 나가지 않게 한다. 호출부는 hashed_password 만 다루면 된다.
    """

    hashed_password: str
    _plaintext: str = field(repr=False)

    def send_to(self, *, name: str, email: str) -> bool:
        """안내 메일을 보내고 성공 여부를 돌려준다. 실패해도 예외를 올리지 않는다."""
        return send_temporary_password(name=name, email=email, temporary_password=self._plaintext)


def issue_temporary_password() -> TemporaryCredential:
    """임시 비밀번호를 만들어 해시와 함께 돌려준다.

    등록(REQ-ADMIN-008)과 재발송(REQ-ADMIN-003)이 같은 방식을 써야 하므로 한곳에 둔다.
    발송은 호출부가 계정을 저장한 뒤 send_to 로 따로 부른다. 저장보다 먼저 보내면
    저장이 실패했을 때 존재하지 않는 계정의 비밀번호를 보내게 된다.
    """
    plaintext = "".join(secrets.choice(_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH))
    return TemporaryCredential(hashed_password=hash_password(plaintext), _plaintext=plaintext)
