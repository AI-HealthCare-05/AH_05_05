from enum import StrEnum


class EvidenceGapSubject(StrEnum):
    MEDICATION = "MEDICATION"
    SUPPLEMENT = "SUPPLEMENT"
    INTERACTION = "INTERACTION"
    UNKNOWN = "UNKNOWN"


class EvidenceGapGuidanceBuilder:
    """근거가 부족할 때 사실을 보태지 않고 다음 행동만 안내한다."""

    def build_active_intake(
        self,
        *,
        medication_names: list[str],
        supplement_names: list[str],
    ) -> str:
        """등록 목록을 바탕으로 한 질문에 추측 없이 다음 확인 행동만 안내한다."""
        sections = [
            self._intake_section(
                title="복약정보",
                names=medication_names,
            ),
            self._intake_section(
                title="영양제 정보",
                names=supplement_names,
            ),
            "확인된 범위\n"
            "- 현재 보유한 승인 규칙과 검색 근거에서 등록된 약·영양제 조합에 관한 "
            "직접 근거를 확인하지 못했습니다.\n"
            "- 등록된 대상 사이의 상호작용을 확인하지 못했습니다.",
            "일반 안내\n"
            "- 등록된 약·영양제는 성분·함량·복용 시점에 따라 서로 영향을 줄 수 있습니다.\n"
            "- 확인 전에는 복용 시작·중단·용량 변경 또는 병용 여부를 임의로 결정하지 마세요.",
            "알 수 없는 범위\n- 상호작용을 확인하지 못했다는 것은 안전하다는 의미는 아닙니다.",
            "의료진·약사에게 확인할 내용\n"
            "- 제품명·성분명·함량·복용 시점\n"
            "- 현재 복용 중인 약과 영양제 목록\n"
            "- 임신·수유·연령·신장/간질환·수술 예정 여부",
        ]
        return "\n\n".join(section for section in sections if section)

    # 공인 확인처는 질문 대상에 따라 고정한다. 기관 이름을 LLM이 만들면 없는 출처가 생긴다.
    _OFFICIAL_SOURCE_LINES = {
        EvidenceGapSubject.MEDICATION: "의약품안전나라에서 허가사항을 확인할 수 있습니다.",
        EvidenceGapSubject.SUPPLEMENT: "식품안전나라에서 기능성 원료 정보를 확인할 수 있습니다.",
    }
    _DEFAULT_OFFICIAL_SOURCE_LINE = "의약품은 의약품안전나라, 건강기능식품은 식품안전나라에서 확인할 수 있습니다."

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

    @staticmethod
    def _intake_section(
        *,
        title: str,
        names: list[str],
    ) -> str:
        unique_names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        if not unique_names:
            return ""
        return title + "\n" + "\n".join(f"- {name}" for name in unique_names)
