import re

from ai_worker.domain.patient_fact_formatter import (
    format_patient_medication,
)
from ai_worker.schemas.chat import (
    ChatAnswerResult,
)
from ai_worker.schemas.enums import (
    ChatIntent,
    SafetyStatus,
)
from ai_worker.schemas.patient import PatientContext
from ai_worker.schemas.safety import SafetyResult


class RuleBasedChatOutputSafetyValidator:
    _MEDICATION_CHANGE_PATTERNS = (
        re.compile(
            r"(?:"
            r"약|복용(?:량)?|용량|횟수|"
            r"아스피린"
            r")"
            r".{0,20}"
            r"(?:"
            r"중단(?:하세요|하십시오)?|"
            r"끊(?:으세요|으십시오)?|"
            r"안\s*먹(?:어도\s*(?:됩니다|돼요))?|"
            r"건너뛰(?:세요|십시오)?|"
            r"증량(?:하세요|하십시오)?|"
            r"감량(?:하세요|하십시오)?|"
            r"늘리(?:세요|십시오)?|"
            r"줄이(?:세요|십시오)?|"
            r"변경(?:하세요|하십시오)|"
            r"바꾸(?:세요|십시오)?"
            r")"
        ),
    )

    _DIAGNOSTIC_PATTERNS = (
        re.compile(
            r"(?:으로|로)\s*"
            r"(?:진단됩니다|판단됩니다)"
        ),
        re.compile(
            r"(?:질환|질병|증후군)의 "
            r"가능성이 높습니다"
        ),
    )

    _TREATMENT_PATTERNS = (
        re.compile(
            r"(?:수술|시술|입원|치료)"
            r".{0,15}"
            r"(?:"
            r"필요합니다|"
            r"시작하세요|"
            r"받으세요"
            r")"
        ),
    )

    async def validate(
        self,
        patient_context: PatientContext,
        result: ChatAnswerResult,
    ) -> SafetyResult:
        if self._has_medication_mismatch(
            patient_context=patient_context,
            result=result,
        ):
            return SafetyResult(
                status=SafetyStatus.BLOCKED,
                reason_codes=[("PATIENT_MEDICATION_MISMATCH")],
                message=("환자 확정 복약정보와 답변 내용이 일치하지 않아 답변을 차단했습니다."),
            )

        if self._matches_any(
            text=result.answer,
            patterns=(self._MEDICATION_CHANGE_PATTERNS),
        ):
            return SafetyResult(
                status=SafetyStatus.BLOCKED,
                reason_codes=[("MEDICATION_CHANGE_INSTRUCTION")],
                message=("복약 변경에 해당하는 표현이 감지되어 답변을 차단했습니다."),
            )

        if self._matches_any(
            text=result.answer,
            patterns=(self._DIAGNOSTIC_PATTERNS),
        ):
            return SafetyResult(
                status=SafetyStatus.BLOCKED,
                reason_codes=["DIAGNOSTIC_ASSERTION"],
                message=("새로운 진단 또는 증상 판단에 해당하는 표현이 감지되어 답변을 차단했습니다."),
            )

        if self._matches_any(
            text=result.answer,
            patterns=(self._TREATMENT_PATTERNS),
        ):
            return SafetyResult(
                status=SafetyStatus.BLOCKED,
                reason_codes=["TREATMENT_DECISION"],
                message=("치료 또는 수술 결정에 해당하는 표현이 감지되어 답변을 차단했습니다."),
            )

        if not self._has_medical_disclaimer(result.answer):
            return SafetyResult(
                status=SafetyStatus.RESTRICTED,
                reason_codes=[("MISSING_MEDICAL_DISCLAIMER")],
                message=("의료진의 진료를 대체하지 않는다는 안내가 필요합니다."),
            )

        return SafetyResult(
            status=SafetyStatus.SAFE,
            message=("채팅 답변 안전성 검사를 통과했습니다."),
        )

    @classmethod
    def _has_medication_mismatch(
        cls,
        patient_context: PatientContext,
        result: ChatAnswerResult,
    ) -> bool:
        if result.intent != ChatIntent.MEDICATION:
            return False

        if not patient_context.medications:
            return False

        normalized_answer = cls._normalize_text(result.answer)

        expected_medications = [
            cls._normalize_text(format_patient_medication(medication)) for medication in (patient_context.medications)
        ]

        return any(expected_medication not in normalized_answer for expected_medication in expected_medications)

    @staticmethod
    def _has_medical_disclaimer(
        answer: str,
    ) -> bool:
        normalized_answer = answer.strip()

        has_medical_reference = any(
            keyword in normalized_answer
            for keyword in (
                "의료진",
                "의사",
                "진료",
            )
        )

        return has_medical_reference and "대체" in normalized_answer

    @classmethod
    def _matches_any(
        cls,
        text: str,
        patterns: tuple[
            re.Pattern[str],
            ...,
        ],
    ) -> bool:
        normalized_text = cls._normalize_spacing(text)

        return any(pattern.search(normalized_text) for pattern in patterns)

    @staticmethod
    def _normalize_spacing(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return re.sub(
            r"\s+",
            "",
            value,
        ).lower()
