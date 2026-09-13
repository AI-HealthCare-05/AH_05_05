from __future__ import annotations

import re

from ai_worker.reports.v11_cards import V11EvidenceCatalog
from ai_worker.reports.v11_spacing_repair import (
    _MAX_BATCH_SOURCE_CHARACTERS,
    SpacingRepairRequest,
    _SpacingField,
    _split_chunks,
    payload_spacing_pattern,
    project_spacing_proposals,
)
from ai_worker.schemas.intake_report_cards import IntakeReportCardsPlan


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
