"""알람 형태·연령 구간·채팅 DTO 검증 규칙. 동작 변경은 없다.

    app/services/alarm_schedule.py     validate_alarm_shape        (김은미님)
    app/services/nutrient_standards.py resolve_age_range           (김은미님)
    app/dtos/chat.py                   normalize_message           (임경수님)
                                       normalize_reason_code       (임경수님)

`validate_alarm_shape` 는 alarm_schedule.py 에서 유일하게 테스트가 없던 함수다.
같은 파일의 `parse_timezone`·`next_occurrence` 는 test_alarm_schedule.py 에 이미
있는데, 그 파일은 **스케줄 계산**이 주제이고 이쪽은 **형태 검증**이라 분리했다.

⭐ 채팅 DTO 는 검증기를 직접 부르지 않고 모델을 생성해서 확인한다. `mode="before"`
검증기가 `Field(min_length=...)` 보다 먼저 돌아, 공백을 붙여 상한을 넘긴 값이
통과하는지가 그 순서에 달려 있다.

DB·픽스처를 쓰지 않는다.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.dtos.chat import ChatFeedbackRequest, SendChatRequest
from app.models.enums import AlarmType, MealSlot
from app.services.alarm_schedule import validate_alarm_shape
from app.services.nutrient_standards import AGE_RANGES, resolve_age_range

# 시간대를 함께 보내야 하는 알람과, 보내면 안 되는 알람.
SLOT_ALARM_TYPES = [AlarmType.MEDICATION, AlarmType.NUTRIENT]
SLOTLESS_ALARM_TYPES = [t for t in AlarmType if t not in SLOT_ALARM_TYPES]


# ─────────────────────────── validate_alarm_shape ───────────────────────────


@pytest.mark.parametrize("alarm_type", SLOT_ALARM_TYPES)
@pytest.mark.parametrize("meal_slot", list(MealSlot))
def test_slot_alarms_accept_every_meal_slot(alarm_type: AlarmType, meal_slot: MealSlot) -> None:
    """복약·영양제는 시간대가 있어야 한다. 네 시간대 모두 허용된다."""
    validate_alarm_shape(alarm_type, meal_slot)


@pytest.mark.parametrize("alarm_type", SLOT_ALARM_TYPES)
def test_slot_alarms_require_a_meal_slot(alarm_type: AlarmType) -> None:
    with pytest.raises(ValueError, match="meal_slot is required for medication and nutrient alarms."):
        validate_alarm_shape(alarm_type, None)


@pytest.mark.parametrize("alarm_type", SLOTLESS_ALARM_TYPES)
def test_other_alarms_accept_no_meal_slot(alarm_type: AlarmType) -> None:
    """진료일정·안내 확인은 시간대 개념이 없다."""
    validate_alarm_shape(alarm_type, None)


@pytest.mark.parametrize("alarm_type", SLOTLESS_ALARM_TYPES)
@pytest.mark.parametrize("meal_slot", list(MealSlot))
def test_other_alarms_reject_a_meal_slot(alarm_type: AlarmType, meal_slot: MealSlot) -> None:
    with pytest.raises(ValueError, match="meal_slot is only allowed for medication and nutrient alarms."):
        validate_alarm_shape(alarm_type, meal_slot)


def test_every_alarm_type_is_covered_by_one_of_the_two_groups() -> None:
    """열거형에 값이 추가되면 자동으로 「시간대 금지」 쪽으로 분류된다.

    함수가 `alarm_type not in slot_alarm_types` 로 판정하기 때문이다. 새 타입이
    시간대를 받아야 한다면 함수를 고쳐야 하고, 이 테스트가 분류 상태를 드러낸다.
    """
    assert set(SLOT_ALARM_TYPES) | set(SLOTLESS_ALARM_TYPES) == set(AlarmType)
    assert set(SLOT_ALARM_TYPES) & set(SLOTLESS_ALARM_TYPES) == set()
    assert SLOTLESS_ALARM_TYPES, "시간대 없는 타입이 하나는 있어야 이 테스트가 의미를 가진다"


# ──────────────────────────── resolve_age_range ────────────────────────────


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (1, "1-2세"),
        (2, "1-2세"),
        (3, "3-5세"),
        (5, "3-5세"),
        (6, "6-8세"),
        (8, "6-8세"),
        (9, "9-11세"),
        (11, "9-11세"),
        (12, "12-14세"),
        (14, "12-14세"),
        (15, "15-18세"),
        (18, "15-18세"),
        (19, "19-29세"),
        (29, "19-29세"),
        (30, "30-49세"),
        (49, "30-49세"),
        (50, "50-64세"),
        (64, "50-64세"),
        (65, "65-74세"),
        (74, "65-74세"),
    ],
)
def test_every_age_range_boundary(age: int, expected: str) -> None:
    """각 구간의 양쪽 끝을 확인한다. `age <= maximum_age` 라 상한이 포함된다."""
    assert resolve_age_range(age) == expected


@pytest.mark.parametrize("age", [75, 76, 100, 120])
def test_ages_past_the_last_range_fall_into_the_open_ended_bucket(age: int) -> None:
    assert resolve_age_range(age) == "75세 이상"


@pytest.mark.parametrize("age", [0, -1, -100])
def test_ages_below_one_are_labelled_as_the_first_range(age: int) -> None:
    """현재 동작 — 0세와 음수가 「1-2세」로 떨어진다. 라벨과 실제가 어긋난다.

    표의 첫 항목이 `(2, "1-2세")` 이고 `age <= 2` 로 판정하므로 0 과 음수도 여기
    들어온다. 신생아 영양제 기준이 표에 없어서 생기는 일이고, 하한 검사도 없다.

    호출부(nutrient_standards 조회 API)가 age 를 어떻게 받는지에 달려 있어 해로운지
    단정하기 어렵다. 잘못된 값이 조용히 유아 기준으로 조회되는 것은 남겨둘 만하다.
    """
    assert resolve_age_range(age) == "1-2세"


def test_the_age_range_table_is_sorted_and_has_no_gaps() -> None:
    """표가 오름차순이어야 첫 일치가 올바른 구간이 된다.

    순서가 뒤섞이면 `for` 가 엉뚱한 구간을 먼저 만나 조용히 틀린 값을 낸다.
    """
    maximums = [maximum for maximum, _ in AGE_RANGES]

    assert maximums == sorted(maximums)
    assert len(set(maximums)) == len(maximums)


def test_the_age_range_table_covers_every_age_up_to_the_last_boundary() -> None:
    """1세부터 마지막 경계까지 빈 나이가 없다."""
    last_boundary = AGE_RANGES[-1][0]
    labels = {resolve_age_range(age) for age in range(1, last_boundary + 1)}

    assert labels == {label for _, label in AGE_RANGES}


# ──────────────────────────── normalize_message ────────────────────────────


def send_chat(**overrides) -> SendChatRequest:
    payload = {"request_id": uuid4(), "message": "이 약 같이 먹어도 되나요?"}
    return SendChatRequest(**{**payload, **overrides})


def test_a_chat_message_is_stripped() -> None:
    assert send_chat(message="  질문입니다  ").message == "질문입니다"


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_a_blank_chat_message_is_rejected(raw: str) -> None:
    """자르기가 먼저라 공백만 넣으면 빈 문자열이 되어 길이 제약에 걸린다."""
    with pytest.raises(ValidationError, match="at least 1 character"):
        send_chat(message=raw)


def test_a_chat_message_at_the_limit_is_accepted_even_with_surrounding_spaces() -> None:
    """⭐ 2000자 + 앞뒤 공백이 통과한다 — 자르기가 길이 검사보다 먼저다.

    순서가 반대라면 공백 때문에 상한을 넘겨 거부됐을 것이다.
    """
    request = send_chat(message=f"  {'가' * 2000}  ")

    assert len(request.message) == 2000


def test_a_chat_message_past_the_limit_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 2000 characters"):
        send_chat(message="가" * 2001)


@pytest.mark.parametrize("field", ["record_id", "conversation_id"])
def test_non_positive_chat_ids_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        send_chat(**{field: 0})


def test_chat_ids_are_optional() -> None:
    request = send_chat()

    assert request.record_id is None
    assert request.conversation_id is None


# ─────────────────────────── normalize_reason_code ───────────────────────────


def test_a_reason_code_is_stripped_and_upper_cased() -> None:
    assert ChatFeedbackRequest(is_like=False, reason_code="  wrong_answer  ").reason_code == "WRONG_ANSWER"


@pytest.mark.parametrize("raw", ["", "   ", "\t"])
def test_a_blank_reason_code_becomes_none(raw: str) -> None:
    """사유를 안 고른 것과 빈 문자열을 구분하지 않는다 — None 하나로 표현한다."""
    assert ChatFeedbackRequest(is_like=False, reason_code=raw).reason_code is None


def test_a_missing_reason_code_stays_none() -> None:
    assert ChatFeedbackRequest(is_like=True).reason_code is None


def test_an_explicit_null_reason_code_stays_none() -> None:
    assert ChatFeedbackRequest(is_like=True, reason_code=None).reason_code is None


def test_reason_code_length_is_measured_after_stripping() -> None:
    assert ChatFeedbackRequest(is_like=False, reason_code=f"  {'A' * 20}  ").reason_code == "A" * 20

    with pytest.raises(ValidationError, match="at most 20 characters"):
        ChatFeedbackRequest(is_like=False, reason_code="A" * 21)


def test_is_like_accepts_null_for_clearing_a_reaction() -> None:
    """좋아요·싫어요를 취소하는 경우다. 필수지만 None 을 받는다."""
    assert ChatFeedbackRequest(is_like=None).is_like is None

    with pytest.raises(ValidationError, match="Field required"):
        ChatFeedbackRequest()


def test_camel_model_accepts_both_camel_case_and_snake_case() -> None:
    """⭐ CamelModel 은 `populate_by_name=True` 라 두 표기를 모두 받는다.

    「snake 는 거절될 것」이라 가정하면 틀린다. 프론트가 camelCase 를 보내고
    테스트·내부 호출이 snake_case 를 쓰는 조합이 그대로 통한다.
    """
    camel = ChatFeedbackRequest(isLike=True, reasonCode=" helpful ")
    snake = ChatFeedbackRequest(is_like=True, reason_code=" helpful ")

    assert camel.reason_code == snake.reason_code == "HELPFUL"
    assert camel.is_like is snake.is_like is True


def test_send_chat_accepts_both_spellings_for_its_ids() -> None:
    request_id = uuid4()

    camel = SendChatRequest(requestId=request_id, message="질문", recordId=7)
    snake = SendChatRequest(request_id=request_id, message="질문", record_id=7)

    assert camel.record_id == snake.record_id == 7
    assert camel.request_id == snake.request_id == request_id
