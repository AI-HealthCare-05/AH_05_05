from enum import StrEnum


class EvidenceGapSubject(StrEnum):
    MEDICATION = "MEDICATION"
    SUPPLEMENT = "SUPPLEMENT"
    INTERACTION = "INTERACTION"
    UNKNOWN = "UNKNOWN"


class EvidenceGapGuidanceBuilder:
    """근거가 부족할 때 사실을 보태지 않고 다음 행동만 안내한다."""

    # 공인 확인처는 질문 대상에 따라 고정한다. 기관 이름을 LLM이 만들면 없는 출처가 생긴다.
    _OFFICIAL_SOURCE_LINES = {
        EvidenceGapSubject.MEDICATION: "의약품안전나라에서 허가사항을 확인할 수 있습니다.",
        EvidenceGapSubject.SUPPLEMENT: "식품안전나라에서 기능성 원료 정보를 확인할 수 있습니다.",
    }
    _DEFAULT_OFFICIAL_SOURCE_LINE = "의약품은 의약품안전나라, 건강기능식품은 식품안전나라에서 확인할 수 있습니다."
    # 어셈블러가 쓰는 맨 제목. 답변 규약의 소제목 목록에는 없는 이름이다.
    _ASSEMBLED_MISSING_HEADING = "근거를 확인하지 못한 항목"
    _NOT_SAFE_LINE = "- 확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다."

    @classmethod
    def as_notice(cls, assembled_answer: str) -> str:
        """조립된 근거 부재 초안을 답변 규약의 소제목과 안전 문구로 정돈한다.

        이 초안은 LLM 재작성을 거치지 않고 그대로 나가므로 여기서 형식을 맞춘다.
        근거 부재 항목은 `assemble`이 마지막에 덧붙이므로 안전 문구도 끝에 붙인다.
        """

        if cls._ASSEMBLED_MISSING_HEADING not in assembled_answer:
            return assembled_answer
        normalized = assembled_answer.replace(
            cls._ASSEMBLED_MISSING_HEADING,
            "✉️ **안내사항**",
        )
        if "안전하다는 뜻은 아닙니다" in normalized:
            return normalized
        return f"{normalized}\n{cls._NOT_SAFE_LINE}"

    def build(
        self,
        *,
        subject: EvidenceGapSubject,
        entity_names: list[str],
        question: str | None = None,
    ) -> str:
        target = self._notice_target(
            subject=subject,
            entity_names=entity_names,
            question=question,
        )
        official_line = self._OFFICIAL_SOURCE_LINES.get(
            subject,
            self._DEFAULT_OFFICIAL_SOURCE_LINE,
        )
        return "\n\n".join(
            [
                f"✉️ **안내사항**\n\n- {target} 관련 자료를 찾지 못했습니다.\n"
                "- 확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다.",
                f"📭 **공식 확인 경로**\n\n- {official_line}",
            ]
        )

    @staticmethod
    def _target_label(
        *,
        subject: EvidenceGapSubject,
        entity_names: list[str],
    ) -> str:
        names = [name.strip() for name in entity_names if name.strip()]
        if subject == EvidenceGapSubject.INTERACTION and len(names) >= 2:
            return " ↔ ".join(names[:2]) + " 조합"
        if names:
            return ", ".join(names)
        return "질문 대상"

    # 인용한 질문이 길면 안내 문구가 읽기 어려워진다.
    _MAX_QUOTED_QUESTION_LENGTH = 40

    @classmethod
    def _notice_target(
        cls,
        *,
        subject: EvidenceGapSubject,
        entity_names: list[str],
        question: str | None = None,
    ) -> str:
        names = [name.strip() for name in entity_names if name.strip()]
        if subject == EvidenceGapSubject.INTERACTION and len(names) >= 2:
            return " ↔ ".join(names[:2])
        if names:
            return ", ".join(names)
        # 대상을 인식하지 못한 질문이다. 질문에서 이름을 뽑아내면 코드가 대상을 판단하는
        # 셈이므로, 사용자가 쓴 문장을 그대로 인용해 무엇을 찾지 못했는지만 알린다.
        quoted = (question or "").strip()
        if quoted and len(quoted) <= cls._MAX_QUOTED_QUESTION_LENGTH:
            return f"「{quoted}」"
        return "질문 대상"
