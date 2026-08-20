import logging

from app.core.email.backends import EmailMessage, EmailSendError
from app.core.email.state import email_backend

logger = logging.getLogger(__name__)

TEMPORARY_PASSWORD_SUBJECT = "[Ozcoding AI Health] 관리자 계정이 생성되었습니다"


def build_temporary_password_mail(*, name: str, email: str, temporary_password: str) -> EmailMessage:
    body = (
        f"{name}님, 안녕하세요.\n"
        "\n"
        "Ozcoding AI Health 관리자 계정이 생성되었습니다.\n"
        "아래 정보로 로그인해 주세요.\n"
        "\n"
        f"  로그인 이메일 : {email}\n"
        f"  임시 비밀번호 : {temporary_password}\n"
        "\n"
        "임시 비밀번호로는 로그인만 가능합니다.\n"
        "첫 로그인 후 비밀번호를 변경해야 관리자 기능을 사용할 수 있습니다.\n"
        "\n"
        "본인이 요청한 적이 없다면 관리자에게 문의해 주세요.\n"
    )
    return EmailMessage(to=email, subject=TEMPORARY_PASSWORD_SUBJECT, body=body)


def send_temporary_password(*, name: str, email: str, temporary_password: str) -> bool:
    """임시 비밀번호 안내 메일을 보낸다. 성공 여부를 돌려준다.

    발송이 실패해도 예외를 올리지 않는다. 계정은 이미 만들어졌고 롤백하지 않기로 했으므로,
    호출한 쪽이 emailSent 로 결과를 응답에 실어 관리자가 상황을 알 수 있게 한다.

    평문 비밀번호는 메시지 안에만 존재한다. 실패 로그에도 남기지 않는다.
    """
    message = build_temporary_password_mail(name=name, email=email, temporary_password=temporary_password)
    try:
        email_backend.send(message)
    except EmailSendError:
        logger.error("temporary password mail failed: to=%s", email)
        return False
    return True
