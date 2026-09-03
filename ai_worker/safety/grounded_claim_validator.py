import re

from ai_worker.llm.assemblers.medication_answer_assembler import (
    MEDICAL_DISCLAIMER,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationChatResult,
)


class RuleBasedGroundedClaimValidator:
    _MEDICATION_CHANGE_PATTERN = re.compile(
        r"(?:약|복용|복용량|용량|횟수|처방)"
        r"[^.!?。！？]{0,40}"
        r"(?:"
        r"(?:중단|시작|변경|증량|감량|건너뛰)"
        r"\s*(?:하세요|하십시오|해야\s*합니다|해도\s*됩니다|해\s*주세요)"
        r"|(?:늘리|줄이)\s*세요"
        r"|끊\s*으세요"
        r")",
        re.IGNORECASE,
    )
    _DIAGNOSIS_PATTERN = re.compile(
        r"(?:으로|로)\s*(?:진단됩니다|판단됩니다)|"
        r"(?:질환|질병|증후군)의\s*가능성이\s*높습니다"
    )
    _TREATMENT_PATTERN = re.compile(
        r"(?:수술|시술|입원|치료)(?:\s*변경)?"
        r"(?:이|가|을|를)?\s*"
        r"(?:필요합니다|시작하세요|받으세요)"
    )

    async def validate(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult:
        del context
        normalized_answer = self._normalize_spacing(result.answer)
        if self._MEDICATION_CHANGE_PATTERN.search(normalized_answer):
            return self._blocked_result(
                result,
                reason_code="MEDICATION_CHANGE_INSTRUCTION",
            )
        if self._DIAGNOSIS_PATTERN.search(normalized_answer):
            return self._blocked_result(
                result,
                reason_code="DIAGNOSTIC_ASSERTION",
            )
        if self._TREATMENT_PATTERN.search(normalized_answer):
            return self._blocked_result(
                result,
                reason_code="TREATMENT_DECISION",
            )
        if not self._has_disclaimer(normalized_answer):
            reason_codes = list(result.safety_reason_codes)
            if "MISSING_MEDICAL_DISCLAIMER" not in reason_codes:
                reason_codes.append("MISSING_MEDICAL_DISCLAIMER")
            return result.model_copy(
                update={
                    "answer": f"{result.answer.rstrip()}\n\n{MEDICAL_DISCLAIMER}",
                    "safety_status": SafetyStatus.RESTRICTED,
                    "safety_reason_codes": reason_codes,
                }
            )
        return result

    @staticmethod
    def _blocked_result(
        result: MedicationChatResult,
        *,
        reason_code: str,
    ) -> MedicationChatResult:
        return result.model_copy(
            update={
                "answer": (
                    "안전성 검사를 통과하지 못해 원래 답변을 제공할 수 "
                    "없습니다. 복용 여부나 용량 변경은 의료진 또는 약사와 "
                    "상의하세요.\n\n"
                    f"{MEDICAL_DISCLAIMER}"
                ),
                "safety_status": SafetyStatus.BLOCKED,
                "safety_reason_codes": [reason_code],
            }
        )

    @staticmethod
    def _has_disclaimer(answer: str) -> bool:
        return "대체" in answer and any(keyword in answer for keyword in ("의료진", "의사", "진료", "약사"))

    @staticmethod
    def _normalize_spacing(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()
