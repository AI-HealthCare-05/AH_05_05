import re
from dataclasses import dataclass
from enum import StrEnum


class MedicationDoseQuestionKind(StrEnum):
    NONE = "NONE"
    OFFICIAL_REFERENCE = "OFFICIAL_REFERENCE"
    PERSONAL_CHANGE = "PERSONAL_CHANGE"
    POSSIBLE_OVERDOSE = "POSSIBLE_OVERDOSE"


@dataclass(frozen=True)
class MedicationDoseQuestionDecision:
    kind: MedicationDoseQuestionKind = MedicationDoseQuestionKind.NONE

    @property
    def requires_confirmation(self) -> bool:
        return self.kind == MedicationDoseQuestionKind.PERSONAL_CHANGE

    @property
    def requires_urgent_guidance(self) -> bool:
        return self.kind == MedicationDoseQuestionKind.POSSIBLE_OVERDOSE

    @property
    def requires_terminal_response(self) -> bool:
        return self.requires_confirmation or self.requires_urgent_guidance


class MedicationDoseQuestionPolicy:
    """용량 관련 질문을 공식 정보 조회와 개인 복용 판단으로 구분한다."""

    _POSSIBLE_OVERDOSE_PATTERN = re.compile(
        r"(?:방금|이미|실수로|잘못).{0,32}?(?:먹었|복용했)|"
        r"(?:두\s*배|과다|초과).{0,24}?(?:먹었|복용했)",
    )
    _PERSONAL_CHANGE_PATTERN = re.compile(
        r"평소보다\s*(?:더|적게|두\s*배)|"
        r"(?:두\s*배|더).{0,20}?(?:먹어도|복용해도|먹을까|복용할까|돼|되)",
    )
    _OFFICIAL_REFERENCE_PATTERN = re.compile(
        r"(?:하루|1일).{0,12}?(?:최대|몇\s*(?:정|캡슐|포|회|mg|밀리그램))|"
        r"최대.{0,12}?(?:용량|복용량|몇\s*(?:정|캡슐|포|회|mg|밀리그램))|"
        r"(?:1일|하루)\s*최대",
    )

    def classify(self, question: str) -> MedicationDoseQuestionDecision:
        normalized = " ".join(question.casefold().split())
        if self._POSSIBLE_OVERDOSE_PATTERN.search(normalized):
            return MedicationDoseQuestionDecision(
                kind=MedicationDoseQuestionKind.POSSIBLE_OVERDOSE,
            )
        if self._PERSONAL_CHANGE_PATTERN.search(normalized):
            return MedicationDoseQuestionDecision(
                kind=MedicationDoseQuestionKind.PERSONAL_CHANGE,
            )
        if self._OFFICIAL_REFERENCE_PATTERN.search(normalized):
            return MedicationDoseQuestionDecision(
                kind=MedicationDoseQuestionKind.OFFICIAL_REFERENCE,
            )
        return MedicationDoseQuestionDecision()
