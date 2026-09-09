from datetime import date

import pytest
from pydantic import ValidationError

from app.dtos.follow_up_visits import FollowUpVisitCreateRequest, FollowUpVisitUpdateRequest


def test_create_requires_hospital() -> None:
    with pytest.raises(ValidationError):
        FollowUpVisitCreateRequest(visit_date=date(2026, 9, 10))


@pytest.mark.parametrize("hospital", [None, "", " \t\n ", "가" * 256], ids=["null", "empty", "blank", "too-long"])
@pytest.mark.parametrize("request_type", [FollowUpVisitCreateRequest, FollowUpVisitUpdateRequest])
def test_requests_reject_invalid_explicit_hospital(request_type, hospital) -> None:
    with pytest.raises(ValidationError):
        request_type(visit_date=date(2026, 9, 10), hospital=hospital)


@pytest.mark.parametrize("hospital", ["내과", "○○이비인후과", "가" * 255], ids=["short-name", "clinic", "max-length"])
@pytest.mark.parametrize("request_type", [FollowUpVisitCreateRequest, FollowUpVisitUpdateRequest])
def test_requests_trim_hospital_before_validating_length(request_type, hospital: str) -> None:
    request = request_type(visit_date=date(2026, 9, 10), hospital=f" \t{hospital}\n ")

    assert request.hospital == hospital
    assert request.visit_time is None


def test_patch_can_omit_hospital_and_explicitly_clear_optional_time() -> None:
    request = FollowUpVisitUpdateRequest(visit_time=None)

    assert request.model_dump(exclude_unset=True) == {"visit_time": None}
