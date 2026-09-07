"""공통코드 정규화 12개 테스트 — 김은미님 코드 대상. 동작 변경은 없다.

    app/services/common_codes.py   normalize_common_code · normalize_common_group_code
    app/dtos/common_codes.py       normalize_code_value + field_validator 9개

문서를 받는 창구 앞의 정리 절차다. 앞뒤 공백을 떼고 대문자로 맞춘 뒤 창구 뒤로 넘긴다.
여기가 틀리면 예외가 나지 않고 조금 다른 문자열이 조용히 통과한다.

DTO 검증기는 `mode="before"` 라 **정규화가 제약 검사보다 먼저** 돈다. 그래서
`" chat "` 처럼 공백이 붙은 값도 통과한다. 그 순서를 모델 생성으로 확인해 고정한다.

DB·픽스처를 쓰지 않는다.
"""

import pytest
from pydantic import ValidationError

from app.core.exceptions import InvalidCommonCodeError
from app.dtos.common_codes import (
    CommonCodeCreateRequest,
    CommonCodeGroupCreateRequest,
    CommonCodeGroupListQuery,
    CommonCodeGroupUpdateRequest,
    CommonCodeListQuery,
    CommonCodeUpdateRequest,
    normalize_code_value,
)
from app.services.common_codes import normalize_common_code, normalize_common_group_code

CODE_NORMALIZERS = [normalize_common_code, normalize_common_group_code]
CODE_NORMALIZER_IDS = ["common_code", "common_group_code"]


# ─────────────── normalize_common_code / normalize_common_group_code ───────────────
#
# 두 함수는 본문이 동일한 복사본이다(정규식 상수만 이름이 다르고 값은 같다).


@pytest.mark.parametrize("normalize", CODE_NORMALIZERS, ids=CODE_NORMALIZER_IDS)
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("USER_STATUS", "USER_STATUS"),
        ("user_status", "USER_STATUS"),
        ("  user_status  ", "USER_STATUS"),
        ("Code01", "CODE01"),
        ("A", "A"),
        ("_", "_"),
        ("0", "0"),
    ],
)
def test_code_normalizer_strips_and_upper_cases(normalize, raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize("normalize", CODE_NORMALIZERS, ids=CODE_NORMALIZER_IDS)
@pytest.mark.parametrize(
    "raw",
    [
        "",  # 빈 문자열 — 정규식이 1자 이상을 요구한다
        "   ",
        "user-status",  # 하이픈
        "user status",  # 가운데 공백
        "user.status",
        "코드",  # 한글
        "CODE!",
        "CODE\n01",
    ],
)
def test_code_normalizer_raises_on_characters_outside_the_pattern(normalize, raw: str) -> None:
    """규칙을 어기면 조용히 통과시키지 않고 InvalidCommonCodeError 를 던진다."""
    with pytest.raises(InvalidCommonCodeError):
        normalize(raw)


@pytest.mark.parametrize("normalize", CODE_NORMALIZERS, ids=CODE_NORMALIZER_IDS)
def test_code_normalizer_is_idempotent(normalize) -> None:
    once = normalize("  user_status  ")

    assert normalize(once) == once


@pytest.mark.parametrize(
    "raw",
    ["USER_STATUS", "user_status", "  code01  ", "A_1", "_", "0"],
)
def test_the_two_code_normalizers_agree(raw: str) -> None:
    """두 함수는 현재 같은 구현이다. 한쪽만 고치면 이 테스트가 알려준다."""
    assert normalize_common_code(raw) == normalize_common_group_code(raw)


@pytest.mark.parametrize("raw", ["", "user-status", "코드"])
def test_the_two_code_normalizers_reject_the_same_inputs(raw: str) -> None:
    for normalize in CODE_NORMALIZERS:
        with pytest.raises(InvalidCommonCodeError):
            normalize(raw)


# ───────────────────────────── normalize_code_value ─────────────────────────────
#
# DTO 쪽 정규화기다. 서비스 쪽 두 함수와 달리 **예외를 던지지 않는다.**


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("user_status", "USER_STATUS"),
        ("  chat  ", "CHAT"),
        ("", ""),
        ("   ", ""),
        ("user-status", "USER-STATUS"),  # 형식은 보지 않는다 — Field(pattern) 이 맡는다
        ("코드", "코드"),
    ],
)
def test_normalize_code_value_strips_and_upper_cases_strings(raw: str, expected: str) -> None:
    assert normalize_code_value(raw) == expected


@pytest.mark.parametrize("raw", [None, 123, 4.5, True, ["A"], {"a": 1}])
def test_normalize_code_value_passes_non_strings_through_untouched(raw: object) -> None:
    """문자열이 아니면 그대로 돌려준다. 형식 판정은 pydantic 이 이어서 한다."""
    assert normalize_code_value(raw) is raw


def test_normalize_code_value_does_not_raise_unlike_the_service_normalizers() -> None:
    """서비스 쪽 두 함수는 규칙 위반에 예외를 던지지만 이쪽은 던지지 않는다.

    이 차이가 의도된 분업이다 — DTO 는 다듬기만 하고, 거부는 Field(pattern) 이 한다.
    """
    assert normalize_code_value("user-status") == "USER-STATUS"
    with pytest.raises(InvalidCommonCodeError):
        normalize_common_code("user-status")


# ──────────────────── field_validator — 정규화가 제약보다 먼저 돈다 ────────────────────


def test_group_list_query_normalizes_codes_before_the_pattern_check() -> None:
    """`mode="before"` 라 공백이 붙고 소문자인 값도 통과한다."""
    query = CommonCodeGroupListQuery(category="  chat  ", group_code="user_status")

    assert query.category == "CHAT"
    assert query.group_code == "USER_STATUS"


def test_group_list_query_still_rejects_values_that_fail_after_normalizing() -> None:
    with pytest.raises(ValidationError):
        CommonCodeGroupListQuery(category="user-status")


def test_group_list_query_leaves_none_alone() -> None:
    query = CommonCodeGroupListQuery()

    assert query.category is None
    assert query.group_code is None


def test_group_list_query_measures_max_length_after_stripping() -> None:
    """20자 + 앞뒤 공백은 통과한다. 자르기가 길이 검사보다 먼저이기 때문이다."""
    query = CommonCodeGroupListQuery(category=f"  {'A' * 20}  ")

    assert query.category == "A" * 20

    with pytest.raises(ValidationError):
        CommonCodeGroupListQuery(category="A" * 21)


def test_group_create_request_normalizes_codes_and_strips_text() -> None:
    request = CommonCodeGroupCreateRequest(
        category="  chat  ",
        group_code="  user_status  ",
        group_name="  회원 상태  ",
        description="  설명  ",
    )

    assert request.category == "CHAT"
    assert request.group_code == "USER_STATUS"
    assert request.group_name == "회원 상태"  # 대문자로 바꾸지 않는다
    assert request.description == "설명"


def test_group_create_request_keeps_inner_spaces_in_text_fields() -> None:
    """strip_text 는 앞뒤만 떼고 가운데 공백은 남긴다 — 사람이 읽는 이름이다."""
    request = CommonCodeGroupCreateRequest(
        category="CHAT",
        group_code="USER_STATUS",
        group_name="  회원  상태  ",
    )

    assert request.group_name == "회원  상태"


def test_group_create_request_rejects_text_that_is_blank_after_stripping() -> None:
    """`min_length=1` 이 자르기 뒤에 걸리므로 공백만 있는 이름은 거부된다."""
    with pytest.raises(ValidationError):
        CommonCodeGroupCreateRequest(category="CHAT", group_code="USER_STATUS", group_name="   ")


def test_group_create_request_allows_a_null_description() -> None:
    request = CommonCodeGroupCreateRequest(category="CHAT", group_code="G", group_name="이름")

    assert request.description is None
    assert request.is_active is True


def test_group_update_request_normalizes_category_and_strips_text() -> None:
    request = CommonCodeGroupUpdateRequest(category="  chat  ", group_name="  이름  ", description="  설명  ")

    assert request.category == "CHAT"
    assert request.group_name == "이름"
    assert request.description == "설명"


def test_group_update_request_accepts_every_field_missing() -> None:
    """부분 수정용이라 전 필드가 선택이다."""
    request = CommonCodeGroupUpdateRequest()

    assert request.category is None
    assert request.group_name is None
    assert request.description is None
    assert request.is_active is None


def test_code_list_query_normalizes_the_detail_code() -> None:
    query = CommonCodeListQuery(detail_code="  active  ")

    assert query.detail_code == "ACTIVE"


def test_code_list_query_does_not_apply_a_pattern_to_the_detail_code() -> None:
    """현재 동작 — 목록 조회의 detail_code 에는 pattern 제약이 없다.

    등록(CommonCodeCreateRequest.detail_code)에는 DETAIL_CODE_PATTERN 이 걸려 있는데
    조회에는 없다. 「찾으려고 넣는 검색어」라 느슨하게 둔 것으로 읽히며, 실제로 이 덕에
    한 글자나 하이픈이 든 값으로도 검색할 수 있다.
    """
    assert CommonCodeListQuery(detail_code="a").detail_code == "A"
    assert CommonCodeListQuery(detail_code="user-status").detail_code == "USER-STATUS"


def test_code_create_request_normalizes_the_detail_code_and_strips_text() -> None:
    request = CommonCodeCreateRequest(
        detail_code="  active  ",
        detail_name="  활성  ",
        description="  설명  ",
    )

    assert request.detail_code == "ACTIVE"
    assert request.detail_name == "활성"
    assert request.description == "설명"
    assert request.sort_order == 0
    assert request.is_active is True


def test_code_create_request_rejects_a_detail_code_that_breaks_the_pattern() -> None:
    with pytest.raises(ValidationError):
        CommonCodeCreateRequest(detail_code="user-status", detail_name="이름")


def test_code_create_request_rejects_a_detail_name_that_is_blank_after_stripping() -> None:
    with pytest.raises(ValidationError):
        CommonCodeCreateRequest(detail_code="ACTIVE", detail_name="   ")


def test_code_update_request_strips_text_only() -> None:
    """수정 요청에는 코드 필드가 없다. 이름·설명만 다듬는다."""
    request = CommonCodeUpdateRequest(detail_name="  활성  ", description="  설명  ")

    assert request.detail_name == "활성"
    assert request.description == "설명"


def test_code_update_request_accepts_every_field_missing() -> None:
    request = CommonCodeUpdateRequest()

    assert request.detail_name is None
    assert request.description is None
    assert request.sort_order is None
    assert request.is_active is None


def test_code_update_request_rejects_a_detail_name_that_is_blank_after_stripping() -> None:
    with pytest.raises(ValidationError):
        CommonCodeUpdateRequest(detail_name="   ")


@pytest.mark.parametrize(
    ("model", "valid_fields"),
    [
        (CommonCodeGroupCreateRequest, {"category": "CHAT", "group_code": "G", "group_name": "이름"}),
        (CommonCodeGroupUpdateRequest, {}),
        (CommonCodeCreateRequest, {"detail_code": "ACTIVE", "detail_name": "이름"}),
        (CommonCodeUpdateRequest, {}),
    ],
    ids=["group_create", "group_update", "code_create", "code_update"],
)
def test_strip_text_leaves_non_strings_to_pydantic(model, valid_fields: dict) -> None:
    """strip_text 는 문자열만 다듬고 나머지는 넘긴다. 타입 판정은 pydantic 이 한다."""
    assert model(**valid_fields) is not None  # 대조군 — 나머지 필드는 문제가 없다

    with pytest.raises(ValidationError):
        model(**valid_fields, description=123)
