import re
from unittest import TestCase

from app.core.utils.security import verify_password
from app.core.validators.user_validators import validate_password
from app.services.admin_credentials import (
    TEMPORARY_PASSWORD_LENGTH,
    generate_temporary_password,
    issue_temporary_password,
)

# 우연히 통과하는 걸 통과로 착각하지 않을 만큼 돌린다.
# 종류별 최소 1개를 보장하기 전에는 12자 기준 약 36% 가 정책을 어겼으므로,
# 200회면 회귀가 들어왔을 때 사실상 확실히 잡힌다.
SAMPLE_COUNT = 200


class TestTemporaryPasswordGeneration(TestCase):
    def test_always_satisfies_password_policy(self) -> None:
        """서버가 자기 정책을 통과하지 못하는 비밀번호를 발급하면 안 된다."""
        for _ in range(SAMPLE_COUNT):
            password = generate_temporary_password()
            validate_password(password)  # 정책 위반이면 ValueError 로 실패한다

    def test_keeps_configured_length(self) -> None:
        for _ in range(SAMPLE_COUNT):
            assert len(generate_temporary_password()) == TEMPORARY_PASSWORD_LENGTH

    def test_required_characters_are_not_always_in_the_same_position(self) -> None:
        """섞지 않으면 앞 4자가 항상 대문자·소문자·숫자·특수문자 순서로 나온다."""
        first_characters = {generate_temporary_password()[0] for _ in range(SAMPLE_COUNT)}

        assert any(re.fullmatch(r"[a-z]", character) for character in first_characters)
        assert any(re.fullmatch(r"[^a-zA-Z0-9]", character) for character in first_characters)

    def test_does_not_repeat(self) -> None:
        assert len({generate_temporary_password() for _ in range(SAMPLE_COUNT)}) == SAMPLE_COUNT


class TestIssueTemporaryPassword(TestCase):
    def test_hash_matches_the_plaintext_that_gets_mailed(self) -> None:
        credential = issue_temporary_password()

        assert verify_password(credential._plaintext, credential.hashed_password)
        validate_password(credential._plaintext)

    def test_repr_hides_the_plaintext(self) -> None:
        """예외 메시지나 로그에 평문이 딸려 나가면 안 된다."""
        credential = issue_temporary_password()

        assert credential._plaintext not in repr(credential)
