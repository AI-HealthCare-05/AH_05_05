"""회원가입 테스트가 이메일 인증 토큰을 얻는 공용 경로.

PR #282 가 SignUpRequest 에 email_verification_token 을 필수로 넣었다. 회원가입을
부르는 테스트는 유효한 토큰을 함께 보내야 한다.

**검증을 건너뛰지 않고 정상 경로를 그대로 태운다.** 실제 EmailVerification 레코드를
만들고 같은 코덱으로 토큰을 발급한다. 임의의 문자열을 넣거나 서비스를 우회하게
만들면 테스트는 통과하는데 인증을 우회하는 형태로 굳는다.

app/tests/auth_apis/test_signup_api.py 의 패턴을 따른다. 그 파일은 자기 토큰을
직접 발급하므로 이 헬퍼를 쓰지 않는다.

⚠️ **토큰은 일회용이다.** validate_signup_token 이 consumed_at 을 확인하고,
회원가입이 성공하면 그 값을 채운다. 그래서 **회원가입마다 새로 발급**해야 한다.
같은 토큰을 두 번 쓰면 두 번째는 거부된다.

비밀키는 app/tests/conftest.py 가 세션 시작에 세운다(전화번호 암호화 키와 같은 방식).
"""

from datetime import datetime, timedelta
from typing import Any

from app.core import config
from app.core.email.verification import EmailVerificationTokenCodec
from app.models.email_verifications import EmailVerification
from app.models.enums import EmailVerificationPurpose

# 실제 코드값은 검사하지 않는다(validate_signup_token 은 verified_at 만 본다).
# 컬럼이 CHAR(64) 라 길이만 맞춘다.
_UNUSED_CODE_DIGEST = "0" * 64


def _codec() -> EmailVerificationTokenCodec:
    """서비스가 만드는 것과 같은 설정의 코덱.

    알고리즘·수명을 config 에서 읽어, 설정이 바뀌면 테스트도 같이 따라간다.
    """
    return EmailVerificationTokenCodec(
        config.EMAIL_VERIFICATION_SECRET,
        algorithm=config.JWT_ALGORITHM,
        ttl_seconds=config.EMAIL_VERIFICATION_TOKEN_TTL_SECONDS,
    )


async def issue_signup_token(email: str) -> str:
    """이메일 하나에 대해 인증을 마친 상태의 가입용 토큰을 발급한다.

    validate_signup_token 이 요구하는 조건을 모두 갖춘다 — purpose 가 SIGNUP,
    verified_at 이 채워져 있고, consumed_at 은 비어 있고, 만료되지 않았다.

    호출할 때마다 새 레코드를 만든다. 토큰이 일회용이기 때문이다.
    """
    now = datetime.now(config.TIMEZONE)
    verification = await EmailVerification.create(
        # validate_signup_token 이 casefold 로 비교하므로 저장도 맞춰 둔다.
        email=email.casefold(),
        purpose=EmailVerificationPurpose.SIGNUP,
        code_digest=_UNUSED_CODE_DIGEST,
        expires_at=now + timedelta(minutes=10),
        verified_at=now,
    )
    return _codec().issue(
        verification_id=verification.id,
        email=email,
        purpose=EmailVerificationPurpose.SIGNUP,
    )


async def with_signup_token(payload: dict[str, Any]) -> dict[str, Any]:
    """회원가입 페이로드에 유효한 토큰을 얹어 돌려준다.

    페이로드의 `email` 을 그대로 쓴다. 원본을 바꾸지 않고 사본을 만든다 —
    같은 dict 를 재사용하는 호출부가 있어도 토큰이 겹치지 않는다.

    이메일이 없거나 문자열이 아니면 토큰만 발급할 수 없으므로 그대로 알려준다.
    """
    email = payload.get("email")
    if not isinstance(email, str):
        raise TypeError("회원가입 페이로드에 문자열 email 이 필요합니다.")

    return {**payload, "email_verification_token": await issue_signup_token(email)}
