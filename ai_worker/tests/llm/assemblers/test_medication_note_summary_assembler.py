from datetime import datetime

from ai_worker.llm.assemblers.medication_note_summary_assembler import (
    MedicationNoteSummaryAssembler,
)
from ai_worker.schemas.medication_note_summary import (
    MedicationNoteEpisodeSummaryPayload,
    MedicationNoteSummaryEpisode,
    MedicationNoteSummaryNote,
    MedicationNoteSummaryNotePayload,
    MedicationNoteSummaryPayload,
    MedicationNoteSummaryScope,
    MedicationNoteSummarySelection,
)


def test_assembler_renders_episode_blocks_and_recent_three_notice() -> None:
    episodes = [
        MedicationNoteSummaryEpisode(
            care_episode_id=index,
            care_episode_alias=f"{chr(64 + index)}병원 진료",
            medication_names=["타이레놀정", "리바록사반정"],
            notes=[
                MedicationNoteSummaryNote(
                    medication_note_id=index * 10,
                    dosed_at=datetime(2026, 9, index, 9, 0),
                    body=f"메모 {index}",
                ),
            ],
        )
        for index in range(1, 4)
    ]
    selection = MedicationNoteSummarySelection(
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
        episodes=episodes,
        has_more_episodes=True,
    )
    payload = MedicationNoteSummaryPayload(
        episodes=[
            MedicationNoteEpisodeSummaryPayload(
                care_episode_id=episode.care_episode_id,
                note_summaries=[
                    MedicationNoteSummaryNotePayload(
                        medication_note_id=episode.notes[0].medication_note_id,
                        summary=f"증상 {episode.care_episode_id}을 기록함.",
                    ),
                ],
                one_line_summary=f"증상 {episode.care_episode_id}을 기록함.",
            )
            for episode in episodes
        ],
    )

    answer = MedicationNoteSummaryAssembler().assemble(
        selection=selection,
        payload=payload,
    )

    assert answer.count("💉 **과거 복약 정보 ·") == 3
    assert "💉 **과거 복약 정보 · A병원 진료**" in answer
    assert "- 타이레놀정" in answer
    assert "📝 **복약메모 요약**" in answer
    assert "- 9월 1일: 증상 1을 기록함." in answer
    assert "⭐️ **한줄 요약**" in answer
    assert "약물 연결 없음" not in answer
    assert "📌 최근 3건의 진료 기록만 정리했습니다. 이전 진료 기록도 필요하면 말씀해 주세요." in answer
