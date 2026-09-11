from ai_worker.domain.intake_display import format_active_medication_names


def test_format_active_medication_names_removes_parenthetical_descriptions_and_duplicates() -> None:
    names = format_active_medication_names(
        [
            "리바록사반정(항응고제)",
            " 리바록사반정 ",
            "파모티딘정（위장약）",
        ]
    )

    assert names == ["리바록사반정", "파모티딘정"]
