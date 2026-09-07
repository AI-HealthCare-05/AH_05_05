"""영양제·복약 메모 DTO 검증 규칙 — 신동훈님 코드 대상. 동작 변경은 없다.

    app/dtos/user_supplement_nutrients.py
      reject_duplicate_slots × 3 · validate_date_range × 3
      normalize_dose_unit × 2 · normalize_note × 2
    app/dtos/medications.py
      normalize_alias · normalize_body × 2 · reject_null_required_updates

창구에서 서류를 받을지 되돌려보낼지 정하는 접수 규칙이다. 정규화(#275)와 달리
**거절한다.** 그래서 무엇이 통과하는지뿐 아니라 **무엇이 어떤 메시지로 막히는지**
까지 고정한다.

⭐ **검증기를 클래스에서 직접 부르지 않고 모델을 생성해서 확인한다.**

`Cls.normalize_x(...)` 로 부르면 pydantic 실행 순서를 건너뛴다. `mode="before"`
검증기는 `Field(min_length=...)` 보다 **먼저** 돌고, `model_validator(mode="after")`
는 필드 검증이 전부 끝난 뒤에 돈다. 이 순서가 동작을 가르므로 모델 생성으로만 본다.

검증기가 ValueError 를 던져도 pydantic 이 감싸 ValidationError 로 나온다.
메시지가 중요한 건은 원문이 들어 있는지도 확인한다.

DB·픽스처를 쓰지 않는다.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.dtos.medications import (
    CreateMedicationNoteRequest,
    UpdateCareEpisodeAliasRequest,
    UpdateMedicationNoteRequest,
)
from app.dtos.user_supplement_nutrients import (
    ManualSupplementNutrientCreateRequest,
    UserSupplementNutrientUpdateRequest,
    UserSupplementNutrientUpsertRequest,
)
from app.models.enums import MealSlot

START = date(2026, 1, 1)

# 세 클래스가 요구하는 필수 필드가 달라 생성 함수를 따로 둔다.
# 필수를 채운 최소 페이로드에 검사할 값만 얹는 방식이다.


def create_request(**overrides) -> ManualSupplementNutrientCreateRequest:
    payload = {
        "custom_name": "종합비타민",
        "dose_amount": "1",
        "dose_unit": "정",
        "start_date": START,
        "slots": [MealSlot.MORNING],
    }
    return ManualSupplementNutrientCreateRequest(**{**payload, **overrides})


def upsert_request(**overrides) -> UserSupplementNutrientUpsertRequest:
    payload = {
        "dose_amount": "1",
        "dose_unit": "정",
        "start_date": START,
        "slots": [MealSlot.MORNING],
    }
    return UserSupplementNutrientUpsertRequest(**{**payload, **overrides})


def update_request(**overrides) -> UserSupplementNutrientUpdateRequest:
    """전 필드가 선택이라 넘긴 것만 담는다."""
    return UserSupplementNutrientUpdateRequest(**overrides)


REQUIRED_SLOT_BUILDERS = [create_request, upsert_request]
REQUIRED_SLOT_IDS = ["manual_create", "upsert"]


# ────────────────────────── reject_duplicate_slots ──────────────────────────


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_duplicate_slots_are_rejected(build) -> None:
    with pytest.raises(ValidationError, match="Duplicate supplement slots are not allowed."):
        build(slots=[MealSlot.MORNING, MealSlot.MORNING])


def test_duplicate_slots_are_rejected_on_update_too() -> None:
    with pytest.raises(ValidationError, match="Duplicate supplement slots are not allowed."):
        update_request(slots=[MealSlot.EVENING, MealSlot.EVENING])


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_all_four_distinct_slots_are_accepted(build) -> None:
    slots = [MealSlot.MORNING, MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME]

    assert build(slots=slots).slots == slots


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_an_empty_slot_list_is_rejected_by_the_length_constraint(build) -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        build(slots=[])


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_more_than_four_slots_is_rejected_by_the_length_constraint(build) -> None:
    """시간대는 네 개뿐이라 다섯 개면 반드시 중복이지만, 길이 제약이 먼저 잡는다.

    `Field(max_length=4)` 가 default-mode 검증기보다 앞서므로 「중복」이 아니라
    「최대 4개」 메시지가 나간다.
    """
    with pytest.raises(ValidationError, match="at most 4 items"):
        build(slots=[MealSlot.MORNING] * 5)


def test_update_accepts_a_missing_slot_list() -> None:
    """부분 수정이라 slots 를 안 보내도 된다."""
    assert update_request().slots is None


def test_update_accepts_an_explicit_null_slot_list() -> None:
    """⭐ 세 사본 중 Update 만 None 을 통과시킨다.

    `reject_duplicate_slots` 에 `value is not None` 가드가 있고 필드 타입도
    `list[MealSlot] | None` 이다.
    """
    assert update_request(slots=None).slots is None


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_create_and_upsert_reject_a_null_slot_list(build) -> None:
    """⭐ Create·Upsert 는 None 을 거부한다 — 필드가 필수라 타입 검증에서 막힌다.

    검증기의 `value is not None` 가드가 없는 것은 여기까지 오지 않기 때문이다.
    세 사본의 차이가 「부분 수정 DTO 만 None 허용」이라는 사양으로 읽힌다.
    """
    with pytest.raises(ValidationError, match="valid list"):
        build(slots=None)


def test_the_three_slot_validators_agree_on_duplicates() -> None:
    """중복 판정 자체는 세 사본이 같다. 한쪽만 고치면 이 테스트가 알려준다."""
    duplicated = [MealSlot.LUNCH, MealSlot.LUNCH]

    for build in (create_request, upsert_request, update_request):
        with pytest.raises(ValidationError, match="Duplicate supplement slots are not allowed."):
            build(slots=duplicated)


# ─────────────────────────── validate_date_range ───────────────────────────


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_an_end_date_before_the_start_date_is_rejected(build) -> None:
    with pytest.raises(ValidationError, match="end_date must be on or after start_date."):
        build(end_date=date(2025, 12, 31))


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_the_same_day_is_accepted_as_the_end_date(build) -> None:
    """하루만 복용하는 경우다. `<` 비교라 같은 날은 걸리지 않는다."""
    assert build(end_date=START).end_date == START


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_a_missing_end_date_is_accepted(build) -> None:
    """종료일 미정이면 비워 둔다."""
    assert build().end_date is None


def test_update_rejects_a_reversed_pair_when_both_dates_are_given() -> None:
    with pytest.raises(ValidationError, match="end_date must be on or after start_date."):
        update_request(start_date=START, end_date=date(2025, 12, 31))


def test_update_accepts_an_end_date_alone_even_if_it_looks_reversed() -> None:
    """현재 동작 — Update 는 start_date 가 없으면 날짜를 비교하지 않는다.

    `self.start_date is not None` 가드가 있어, 종료일만 보내면 DTO 는 통과한다.
    비교할 시작일을 요청만 보고는 알 수 없기 때문이다.

    실제 역전은 서비스가 막는다 — user_supplement_nutrients.py:209-217 이 저장된
    레코드 값과 병합한 뒤 `merged_end_date < merged_start_date` 를 검사해 422 를 낸다.
    DTO 가 느슨한 것은 그 분업 때문으로 읽힌다.
    """
    assert update_request(end_date=date(2025, 12, 31)).end_date == date(2025, 12, 31)


def test_update_accepts_a_start_date_alone() -> None:
    assert update_request(start_date=START).start_date == START


# ──────────────────────────── normalize_dose_unit ────────────────────────────


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_dose_unit_is_stripped(build) -> None:
    assert build(dose_unit="  정  ").dose_unit == "정"


def test_update_strips_the_dose_unit_too() -> None:
    assert update_request(dose_unit="  mL  ").dose_unit == "mL"


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_a_whitespace_only_dose_unit_is_rejected_with_a_length_message(build) -> None:
    """현재 동작 — 공백만 넣으면 영문 길이 메시지가 나간다.

    `mode="before"` 정규화가 먼저 돌아 `""` 가 되고, 그 다음 `Field(min_length=1)`
    이 잡는다. 그래서 사용자에게는 「1자 이상이어야 한다」로 보이고 「공백만으로는
    안 된다」는 이유가 드러나지 않는다.

    복약 메모(normalize_body)는 같은 상황에서 한글 메시지를 내므로 두 DTO 의 처리가
    다르다. 해롭지는 않아 현재 동작으로 고정한다.
    """
    with pytest.raises(ValidationError, match="at least 1 character"):
        build(dose_unit="   ")


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_dose_unit_length_is_measured_after_stripping(build) -> None:
    """20자 + 앞뒤 공백은 통과한다 — 자르기가 길이 검사보다 먼저다."""
    assert build(dose_unit=f"  {'가' * 20}  ").dose_unit == "가" * 20

    with pytest.raises(ValidationError, match="at most 20 characters"):
        build(dose_unit="가" * 21)


# ────────────────────────────── normalize_note ──────────────────────────────


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_a_note_is_stripped(build) -> None:
    assert build(note="  아침에 복용  ").note == "아침에 복용"


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_a_blank_note_becomes_none(build, raw: str) -> None:
    """빈 메모를 빈 문자열로 저장하지 않는다. 「없음」은 None 하나로 표현한다."""
    assert build(note=raw).note is None


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_a_missing_note_stays_none(build) -> None:
    assert build().note is None


def test_update_normalizes_both_note_and_review_body() -> None:
    """Update 는 후기 본문도 같은 검증기를 쓴다."""
    request = update_request(note="  메모  ", review_body="  후기  ")

    assert request.note == "메모"
    assert request.review_body == "후기"

    blank = update_request(note="   ", review_body="   ")

    assert blank.note is None
    assert blank.review_body is None


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_note_length_is_measured_after_stripping(build) -> None:
    assert len(build(note=f"  {'가' * 500}  ").note) == 500

    with pytest.raises(ValidationError, match="at most 500 characters"):
        build(note="가" * 501)


# ─────────────────────────────── dose_amount ───────────────────────────────


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
@pytest.mark.parametrize("amount", ["0", "-1", "-0.001"])
def test_a_non_positive_dose_amount_is_rejected(build, amount: str) -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        build(dose_amount=amount)


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_three_decimal_places_are_accepted(build) -> None:
    assert build(dose_amount="1.005").dose_amount == Decimal("1.005")


@pytest.mark.parametrize("build", REQUIRED_SLOT_BUILDERS, ids=REQUIRED_SLOT_IDS)
def test_four_decimal_places_are_rejected(build) -> None:
    with pytest.raises(ValidationError, match="decimal places"):
        build(dose_amount="1.0005")


def test_update_rejects_a_non_positive_dose_amount() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        update_request(dose_amount="0")


def test_update_forbids_unknown_fields() -> None:
    """전 필드가 선택이라 모르는 키를 무시하면 「바꿀 항목 0개」로 성공 응답이 나간다.

    그래서 extra="forbid" 다. 오타(dose_unti)가 저장 성공으로 보이지 않는다.
    """
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        update_request(dose_unti="정")


# ─────────────────────────────── normalize_alias ───────────────────────────────


def test_alias_is_stripped() -> None:
    assert UpdateCareEpisodeAliasRequest(alias="  아침 약  ").alias == "아침 약"


@pytest.mark.parametrize("raw", ["", "   ", "\t"])
def test_a_blank_alias_becomes_none(raw: str) -> None:
    """별명을 지우는 동작이다. 빈 문자열로 저장하지 않는다."""
    assert UpdateCareEpisodeAliasRequest(alias=raw).alias is None


def test_an_explicit_null_alias_stays_none() -> None:
    assert UpdateCareEpisodeAliasRequest(alias=None).alias is None


def test_the_alias_field_is_required_even_though_it_accepts_null() -> None:
    """현재 동작 — `alias` 에 기본값이 없어 **반드시 보내야** 한다.

    `alias: str | None = Field(max_length=50)` 이라 타입은 None 을 받지만 필드
    자체는 필수다. 그래서 「지우기」(None·공백)와 「안 보내기」가 섞일 여지가 없다 —
    안 보내면 422 다. 별명만 바꾸는 전용 API 라 값을 항상 받는 것이 자연스럽다.
    """
    with pytest.raises(ValidationError, match="Field required"):
        UpdateCareEpisodeAliasRequest()


def test_alias_length_is_measured_after_stripping() -> None:
    assert UpdateCareEpisodeAliasRequest(alias=f"  {'가' * 50}  ").alias == "가" * 50

    with pytest.raises(ValidationError, match="at most 50 characters"):
        UpdateCareEpisodeAliasRequest(alias="가" * 51)


# ─────────────────────────────── normalize_body ───────────────────────────────

DOSED_AT = datetime(2026, 1, 1, 9, 0)


def create_note(**overrides) -> CreateMedicationNoteRequest:
    payload = {"care_episode_id": 1, "dosed_at": DOSED_AT, "body": "속이 편했다"}
    return CreateMedicationNoteRequest(**{**payload, **overrides})


def test_a_note_body_is_stripped() -> None:
    assert create_note(body="  속이 편했다  ").body == "속이 편했다"


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_a_blank_note_body_is_rejected_with_the_korean_message(raw: str) -> None:
    """현재 동작 — 검증기가 직접 거절해 한글 메시지가 나간다.

    `mode="before"` 라 `Field(min_length=1)` 보다 먼저 돌고, 그래서 문자열 입력에
    대해서는 길이 제약이 사실상 도달하지 않는다. 두 규칙의 역할이 겹치지만 사용자에게
    가는 문구가 한글이라 이쪽이 더 낫다 — 영양제 dose_unit 은 반대로 영문이 나간다.
    """
    with pytest.raises(ValidationError, match="복약 메모 내용을 입력해주세요."):
        create_note(body=raw)


def test_note_body_length_is_measured_after_stripping() -> None:
    assert len(create_note(body=f"  {'가' * 500}  ").body) == 500

    with pytest.raises(ValidationError, match="at most 500 characters"):
        create_note(body="가" * 501)


def test_a_note_body_is_required_on_create() -> None:
    with pytest.raises(ValidationError, match="Field required"):
        CreateMedicationNoteRequest(care_episode_id=1, dosed_at=DOSED_AT)


@pytest.mark.parametrize("episode_id", [0, -1])
def test_a_non_positive_care_episode_id_is_rejected(episode_id: int) -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        create_note(care_episode_id=episode_id)


# ─────────────────────── reject_null_required_updates ───────────────────────
#
# model_fields_set 으로 「안 보냄」과 「null 을 보냄」을 구분한다.


def test_an_empty_update_is_accepted() -> None:
    """⭐ 아무것도 안 보내면 통과한다 — 바꿀 것이 없다는 뜻이다."""
    request = UpdateMedicationNoteRequest()

    assert request.body is None
    assert request.dosed_at is None
    assert request.medication_id is None


def test_an_explicit_null_body_is_rejected() -> None:
    """⭐ null 을 보내면 거부한다 — 메모를 비우겠다는 요청은 받지 않는다.

    안 보낸 것과 구분하려고 model_fields_set 을 본다.
    """
    with pytest.raises(ValidationError, match="복약 메모 내용을 입력해주세요."):
        UpdateMedicationNoteRequest(body=None)


def test_an_explicit_null_dosed_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="복용 일시는 비워둘 수 없습니다."):
        UpdateMedicationNoteRequest(dosed_at=None)


def test_a_body_only_update_is_accepted() -> None:
    request = UpdateMedicationNoteRequest(body="  수정한 메모  ")

    assert request.body == "수정한 메모"
    assert request.dosed_at is None


def test_a_blank_body_on_update_is_rejected_with_the_korean_message() -> None:
    with pytest.raises(ValidationError, match="복약 메모 내용을 입력해주세요."):
        UpdateMedicationNoteRequest(body="   ")


def test_an_explicit_null_medication_id_is_accepted_on_update() -> None:
    """약 연결을 끊는 것은 허용된다 — 선택 항목이라 필수 목록에 없다."""
    request = UpdateMedicationNoteRequest(medication_id=None)

    assert request.medication_id is None
