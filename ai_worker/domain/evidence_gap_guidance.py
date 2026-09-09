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
            "직접 근거를 확인하지 못했습니다.",
            "일반 안내\n"
            "- 등록된 약·영양제는 성분·함량·복용 시점에 따라 서로 영향을 줄 수 있습니다.\n"
            "- 확인 전에는 복용 시작·중단·용량 변경 또는 병용 여부를 임의로 결정하지 마세요.",
            "알 수 없는 범위\n"
            "- 근거를 찾지 못한 사실만 확인했으며, 해당 조합이 안전하다고 결론낼 수는 없습니다.",
            self._official_route(EvidenceGapSubject.INTERACTION),
            "의료진·약사에게 확인할 내용\n"
            "- 제품명·성분명·함량·복용 시점\n"
            "- 현재 복용 중인 약과 영양제 목록\n"
            "- 임신·수유·연령·신장/간질환·수술 예정 여부",
        ]
        return "\n\n".join(section for section in sections if section)

    def build(
        self,
        *,
        subject: EvidenceGapSubject,
        entity_names: list[str],
    ) -> str:
        target = self._target_label(subject=subject, entity_names=entity_names)
        return "\n\n".join(
            [
                "확인된 범위\n"
                f"- 현재 보유한 승인 규칙과 검색 근거에서 {target}에 관한 "
                "직접 근거를 확인하지 못했습니다.",
                "일반 안내\n- 확인 전에는 복용 시작·중단·용량 변경 또는 병용 여부를 임의로 결정하지 마세요.",
                "알 수 없는 범위\n"
                "- 근거를 찾지 못한 사실만 확인했으며, 해당 대상에 문제가 "
                "없다고 결론낼 수는 없습니다.",
                self._official_route(subject),
                "의료진·약사에게 확인할 내용\n"
                "- 제품명·성분명·함량·복용 시점\n"
                "- 현재 복용 중인 약과 영양제 목록\n"
                "- 임신·수유·연령·신장/간질환·수술 예정 여부",
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

    @staticmethod
    def _intake_section(
        *,
        title: str,
        names: list[str],
    ) -> str:
        unique_names = list(
            dict.fromkeys(name.strip() for name in names if name.strip())
        )
        if not unique_names:
            return ""
        return title + "\n" + "\n".join(f"- {name}" for name in unique_names)

    @staticmethod
    def _official_route(subject: EvidenceGapSubject) -> str:
        if subject == EvidenceGapSubject.MEDICATION:
            return "공식 확인 경로\n- 의약품안전나라에서 제품명 또는 성분명을 확인하세요."
        if subject == EvidenceGapSubject.SUPPLEMENT:
            return "공식 확인 경로\n- 식품안전나라에서 건강기능식품 또는 기능성 원료 정보를 확인하세요."
        return (
            "공식 확인 경로\n"
            "- 의약품은 의약품안전나라에서 제품명 또는 성분명을 확인하세요.\n"
            "- 영양제는 식품안전나라에서 건강기능식품 또는 기능성 원료 정보를 확인하세요."
        )
