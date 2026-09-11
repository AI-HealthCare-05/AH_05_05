from ai_worker.schemas.medication_note_summary import (
    MedicationNoteEpisodeSummaryPayload,
    MedicationNoteSummaryEpisode,
    MedicationNoteSummaryPayload,
    MedicationNoteSummarySelection,
)

_FACTUAL_DISCLAIMER = (
    "※ 위 내용은 사용자가 기록한 사실을 요약한 것이며, 약물과의 관련성을 판단한 내용은 아닙니다."
)
_RECENT_THREE_NOTICE = "📌 최근 3건의 진료 기록만 정리했습니다. 이전 진료 기록도 필요하면 말씀해 주세요."


class MedicationNoteSummaryAssembler:
    """검증된 요약 JSON을 사용자가 합의한 Markdown으로만 렌더링한다."""

    def assemble(
        self,
        *,
        selection: MedicationNoteSummarySelection,
        payload: MedicationNoteSummaryPayload,
    ) -> str:
        payload_by_episode = {
            episode.care_episode_id: episode for episode in payload.episodes
        }
        blocks = [
            self._episode_block(
                episode=episode,
                payload=payload_by_episode[episode.care_episode_id],
            )
            for episode in selection.episodes
        ]
        answer = "\n\n---\n\n".join(blocks)
        if selection.has_more_episodes:
            answer = f"{answer}\n\n{_RECENT_THREE_NOTICE}"
        return answer

    @staticmethod
    def _episode_block(
        *,
        episode: MedicationNoteSummaryEpisode,
        payload: MedicationNoteEpisodeSummaryPayload,
    ) -> str:
        note_summaries = {
            item.medication_note_id: item.summary
            for item in payload.note_summaries
        }
        medications = episode.medication_names or ["등록된 약 정보가 없습니다."]
        medication_lines = "\n".join(f"- {name}" for name in medications)
        note_lines = "\n".join(
            f"- {note.dosed_at.month}월 {note.dosed_at.day}일: "
            f"{note_summaries[note.medication_note_id]}"
            for note in episode.notes
        )
        return "\n\n".join(
            [
                f"💉 **과거 복약 정보 · {MedicationNoteSummaryAssembler._episode_title(episode)}**",
                medication_lines,
                "---",
                "📝 **복약메모 요약**",
                note_lines,
                "⭐️ **한줄 요약**\n" + payload.one_line_summary,
                _FACTUAL_DISCLAIMER,
            ]
        )

    @staticmethod
    def _episode_title(episode: MedicationNoteSummaryEpisode) -> str:
        if episode.care_episode_alias and episode.care_episode_alias.strip():
            return episode.care_episode_alias.strip()
        if episode.hospital_name and episode.hospital_name.strip():
            return f"{episode.hospital_name.strip()} 진료"
        latest_note = max(episode.notes, key=lambda note: note.dosed_at)
        return f"{latest_note.dosed_at.year}년 {latest_note.dosed_at.month}월 진료"
