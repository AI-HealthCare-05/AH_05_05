from __future__ import annotations

import re

import pytest

from ai_worker.reports.v11_cards import V11EvidenceCatalog
from ai_worker.reports.v11_spacing_repair import (
    _MAX_BATCH_SOURCE_CHARACTERS,
    SpacingRepairRequest,
    _SpacingField,
    _split_chunks,
    payload_spacing_pattern,
    project_spacing_proposals,
    source_spacing_pattern,
)
from ai_worker.schemas.intake_report_cards import IntakeReportCardsPlan


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "다른비스테로이드성소염진통제 및나프록센유도체와 함께복용하지마십시오. "
            "히단토인계항간질제, 설파제, 설포닐요소계혈당강하제, 프로프라놀롤및다른β-차단제, "
            "ACE저해제(캅토프릴등), 루프계및티아지드계이뇨제, 프로베네시드, 아스피린, 리튬, "
            "메토트렉세이트, 쿠마린계항응혈제(와파린등), 지도부딘, "
            "뉴퀴놀론계항생물질(에녹사신등)과 함께 복용시 의사또는약사와상의하십시오.",
            "다른 비스테로이드성 소염진통제 및 나프록센 유도체와 함께 복용하지 마십시오. "
            "히단토인계 항간질제, 설파제, 설포닐요소계 혈당강하제, 프로프라놀롤 및 다른β-차단제, "
            "ACE저해제(캅토프릴 등), 루프계 및 티아지드계 이뇨제, 프로베네시드, 아스피린, 리튬, "
            "메토트렉세이트, 쿠마린계 항응혈제(와파린 등), 지도부딘, "
            "뉴퀴놀론계 항생물질(에녹사신 등)과 함께 복용 시 의사 또는 약사와 상의하십시오.",
        ),
        (
            "이약또는다른살리실산제제, 진통제, 소염제, 항류마티스제에대한과민증환자, "
            "소화성궤양, 아스피린천식또는경험자, 혈우병, 심한간장애, 심한신장애, "
            "심한심기능부전, 출혈경향, 일주일동안메토트렉세이트15밀리그람(15mg/주)이상의용량을"
            "병용투여하는환자, 임신3기에해당하는임부는복용하지마십시오. "
            "임신1기와2기에는반드시필요한경우가아니라면 이약을복용하지마십시오.",
            "이 약 또는 다른 살리실산 제제, 진통제, 소염제, 항류마티스제에 대한 과민증 환자, "
            "소화성 궤양, 아스피린 천식 또는 경험자, 혈우병, 심한 간장애, 심한 신장애, "
            "심한 심기능 부전, 출혈 경향, 일주일 동안 메토트렉세이트 15밀리그람(15mg/주)이상의 용량을 "
            "병용 투여하는 환자, 임신 3기에 해당하는 임부는 복용하지 마십시오. "
            "임신 1기와 2기에는 반드시 필요한 경우가 아니라면 이 약을 복용하지 마십시오.",
        ),
    ],
)
def test_user_long_warnings_preserve_every_character_across_chunks(source: str, expected: str) -> None:
    request = _request_for(source)
    assert len(request._fields[0].chunks) > 1
    response = project_spacing_proposals(request.payload(), {"f0": expected})
    positions = request.validate_batch_response(request._all_batch(), response)[0]
    actual = request._joined_field_text(request._fields[0], positions)
    assert actual == expected
    assert re.sub(r"\s", "", actual) == re.sub(r"\s", "", source)


def test_numeric_word_boundaries_do_not_split_doses_units_or_entities() -> None:
    pattern = source_spacing_pattern("성인및12세이상은1일1회120mg을복용합니다.&gamma;")
    assert re.fullmatch(pattern, "성인 및 12세 이상은 1일 1회 120mg을 복용합니다.&gamma;")
    for unsafe in ("1 20mg", "120 mg", "120m g"):
        assert not re.fullmatch(pattern, f"성인및12세이상은1일1회{unsafe}을복용합니다.&gamma;")


def test_spacing_pattern_does_not_split_known_compound_medical_terms() -> None:
    source = "이약에과민증환자는복용하지마십시오."
    pattern = source_spacing_pattern(source)

    assert re.fullmatch(pattern, "이 약에 과민증 환자는 복용하지 마십시오.")
    assert not re.fullmatch(pattern, "이 약에 과 민증 환자는 복용하지 마십시오.")


def _long_source() -> str:
    return (
        "이약은복용하지마십시오.성인은120mg을복용하고&gamma;값을확인합니다." * 120
        + "마지막꼬리문장은누락없이보존되어야합니다."
    )


def _request_for(text: str) -> SpacingRepairRequest:
    chunks = _split_chunks(text)
    assert chunks is not None
    return SpacingRepairRequest(
        IntakeReportCardsPlan(),
        V11EvidenceCatalog(medications={}, interactions=(), lifestyle=(), sources=()),
        [_SpacingField(path=("test",), plan_key=("test",), canonical=text, chunks=chunks)],
    )


def test_long_source_over_4000_is_losslessly_chunked_with_its_final_tail() -> None:
    source = _long_source()

    chunks = _split_chunks(source)

    assert len(source) > 4_000
    assert chunks is not None
    assert "".join(chunks) == source
    assert chunks[-1].endswith("마지막꼬리문장은누락없이보존되어야합니다.")
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_long_unbreakable_numeric_token_fails_closed_without_truncation() -> None:
    source = "1" * 4_100 + "mg"

    assert _split_chunks(source) is None


def test_long_source_uses_bounded_batches_without_omitting_or_splitting_protected_tokens() -> None:
    source = _long_source()
    request = _request_for(source)

    batches = request.batches()
    payloads = [request.payload(batch) for batch in batches]
    sent_chunks = [chunk for payload in payloads for field in payload for chunk in field["chunks"]]

    assert len(batches) > 1
    assert all(
        sum(len(chunk["text"]) for field in payload for chunk in field["chunks"]) <= _MAX_BATCH_SOURCE_CHARACTERS
        for payload in payloads
    )
    assert [chunk["index"] for chunk in sent_chunks] == list(range(len(_split_chunks(source) or [])))
    assert "".join(chunk["text"] for chunk in sent_chunks) == source
    assert all("120" not in chunk["text"] or "120mg" in chunk["text"] for chunk in sent_chunks)
    assert all("&gam" not in chunk["text"] or "&gamma;" in chunk["text"] for chunk in sent_chunks)
    offset = 0
    for chunk in sent_chunks:
        assert not any(
            "하지" in source[offset + position - 1 : offset + position + 1] for position in chunk["allowedSpaceAfter"]
        )
        offset += len(chunk["text"])


def test_batch_seam_can_select_only_a_globally_safe_space_without_changing_source() -> None:
    source = "이약을복용합니다"
    request = SpacingRepairRequest(
        IntakeReportCardsPlan(),
        V11EvidenceCatalog(medications={}, interactions=(), lifestyle=(), sources=()),
        [
            _SpacingField(
                path=("test",),
                plan_key=("test",),
                canonical=source,
                chunks=["이약을복용", "합니다"],
            )
        ],
    )
    fields = request.payload(((0, 0),))

    assert re.fullmatch(payload_spacing_pattern(fields[0]["chunks"]), "이약을복용 ")
    assert project_spacing_proposals(fields, {"f0": "이약을복용 "}) == {
        "repairs": [{"key": "test", "chunks": [{"index": 0, "spaceAfter": [5]}]}]
    }
