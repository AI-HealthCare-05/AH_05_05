from __future__ import annotations

import random

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.pipeline import preprocess


def _candidate(quad, confidence: float = 0.8) -> preprocess._QuadCandidate:
    return preprocess._QuadCandidate(quad, confidence, 0.5, False)


def _quad(x: float, y: float, width: float, height: float):
    return (
        Point(x, y),
        Point(x + width, y),
        Point(x + width, y + height),
        Point(x, y + height),
    )


def _legacy_group_nested_candidates(
    candidates: list[preprocess._QuadCandidate],
) -> list[list[preprocess._QuadCandidate]]:
    groups: list[list[preprocess._QuadCandidate]] = []
    for candidate in candidates:
        matching = [
            index
            for index, group in enumerate(groups)
            if any(preprocess._quad_overlap(candidate.quad, existing.quad) >= 0.55 for existing in group)
        ]
        if not matching:
            groups.append([candidate])
            continue
        target = groups[matching[0]]
        target.append(candidate)
        for index in reversed(matching[1:]):
            target.extend(groups.pop(index))
    return groups


def _group_indices(
    groups: list[list[preprocess._QuadCandidate]],
    candidates: list[preprocess._QuadCandidate],
) -> list[list[int]]:
    positions = {id(candidate): index for index, candidate in enumerate(candidates)}
    return [[positions[id(candidate)] for candidate in group] for group in groups]


def test_nested_grouping_reuses_quad_overlap_work(monkeypatch) -> None:
    candidates = [_candidate(_quad(index * 3, 0, 100, 100)) for index in range(24)]
    overlap_calls = 0
    array_calls = 0
    area_calls = 0
    real_overlap = preprocess._quad_overlap
    real_quad_array = preprocess._quad_array
    real_signed_area = preprocess._signed_area

    def counted_overlap(first, second):
        nonlocal overlap_calls
        overlap_calls += 1
        return real_overlap(first, second)

    def counted_quad_array(quad):
        nonlocal array_calls
        array_calls += 1
        return real_quad_array(quad)

    def counted_signed_area(quad):
        nonlocal area_calls
        area_calls += 1
        return real_signed_area(quad)

    monkeypatch.setattr(preprocess, "_quad_overlap", counted_overlap)
    monkeypatch.setattr(preprocess, "_quad_array", counted_quad_array)
    monkeypatch.setattr(preprocess, "_signed_area", counted_signed_area)

    groups = preprocess._group_nested_candidates(candidates)

    assert _group_indices(groups, candidates) == [list(range(len(candidates)))]
    assert overlap_calls == 0
    assert array_calls == 2 * len(candidates)
    assert area_calls == len(candidates)


def test_nested_grouping_matches_legacy_for_bridging_and_degenerate_quads() -> None:
    candidates = [
        _candidate(_quad(0, 0, 100, 100)),
        _candidate(_quad(300, 0, 100, 100)),
        _candidate(_quad(0, 0, 400, 100)),
        _candidate(_quad(800, 0, 0, 100)),
        _candidate(_quad(1200, 0, 100, 100)),
    ]

    expected = _legacy_group_nested_candidates(candidates)
    actual = preprocess._group_nested_candidates(candidates)

    assert _group_indices(actual, candidates) == _group_indices(expected, candidates)
    assert _group_indices(actual, candidates) == [[0, 2, 1], [3], [4]]


def test_nested_grouping_matches_legacy_for_deterministic_random_quads() -> None:
    randomizer = random.Random(81005)
    candidates = []
    for _ in range(64):
        x = randomizer.randrange(0, 900, 25)
        y = randomizer.randrange(0, 500, 25)
        width = randomizer.choice([0, 50, 75, 100, 150, 200])
        height = randomizer.choice([0, 40, 60, 100, 140])
        candidates.append(_candidate(_quad(x, y, width, height)))

    expected = _legacy_group_nested_candidates(candidates)
    actual = preprocess._group_nested_candidates(candidates)

    assert _group_indices(actual, candidates) == _group_indices(expected, candidates)


def test_nested_grouping_handles_empty_and_singleton_candidates() -> None:
    candidate = _candidate(_quad(10, 20, 30, 40))

    assert preprocess._group_nested_candidates([]) == []
    assert preprocess._group_nested_candidates([candidate]) == [[candidate]]
