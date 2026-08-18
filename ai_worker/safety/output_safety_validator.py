import re

from ai_worker.domain.patient_fact_formatter import (
    format_patient_medication,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.guide import (
    RecoveryGuideResult,
)
from ai_worker.schemas.patient import PatientContext
from ai_worker.schemas.safety import SafetyResult


class RuleBasedOutputSafetyValidator:
    _MEDICATION_CHANGE_PATTERNS = [
        re.compile(
            r"(?:약|복용|복용량|용량|횟수)"
            r".{0,20}"
            r"(?:"
            r"중단(?:하세요|하십시오)|"
            r"끊(?:으세요|으십시오)|"
            r"늘리(?:세요|십시오)|"
            r"줄이(?:세요|십시오)|"
            r"변경(?:하세요|하십시오)|"
            r"바꾸(?:세요|십시오)"
            r")"
        )
    ]

    _DIAGNOSTIC_PATTERNS = [
        re.compile(
            r"(?:으로|로)\s*"
            r"(?:진단됩니다|판단됩니다)"
        ),
        re.compile(
            r"(?:질환|질병|증후군)의 "
            r"가능성이 높습니다"
        ),
    ]

    _TREATMENT_PATTERNS = [
        re.compile(
            r"(?:수술|시술|입원|치료)"
            r".{0,15}"
            r"(?:"
            r"필요합니다|"
            r"시작하세요|"
            r"받으세요"
            r")"
        )
    ]

    async def validate(
        self,
        patient_context: PatientContext,
        result: RecoveryGuideResult,
    ) -> SafetyResult:
        reason_codes: list[str] = []

        if self._has_medication_mismatch(
                patient_context=patient_context,
                result=result,
        ):
            reason_codes.append(
                "PATIENT_MEDICATION_MISMATCH"
            )

        for text in self._collect_guide_texts(
                result
        ):
            if self._is_confirmed_instruction(
                text=text,
                patient_context=patient_context,
            ):
                continue

            if self._matches_any(
                text,
                self._MEDICATION_CHANGE_PATTERNS,
            ):
                reason_codes.append(
                    "MEDICATION_CHANGE_INSTRUCTION"
                )

            if (
                self._matches_any(
                    text,
                    self._DIAGNOSTIC_PATTERNS,
                )
                and not self._contains_confirmed_diagnosis(
                    text=text,
                    patient_context=patient_context,
                )
            ):
                reason_codes.append(
                    "DIAGNOSTIC_ASSERTION"
                )

            if self._matches_any(
                text,
                self._TREATMENT_PATTERNS,
            ):
                reason_codes.append(
                    "TREATMENT_DECISION"
                )

        reason_codes = list(
            dict.fromkeys(reason_codes)
        )

        if reason_codes:
            return SafetyResult(
                status=SafetyStatus.BLOCKED,
                reason_codes=reason_codes,
                message=(
                    "의학적 판단 또는 약 변경에 "
                    "해당하는 표현이 감지되어 "
                    "출력을 차단했습니다."
                ),
            )

        safety_notice = (
            result.guide_content.safety_notice
        )

        if not self._has_medical_disclaimer(
            safety_notice
        ):
            return SafetyResult(
                status=SafetyStatus.RESTRICTED,
                reason_codes=[
                    "MISSING_MEDICAL_DISCLAIMER"
                ],
                message=(
                    "의료진의 진료를 대체하지 "
                    "않는다는 안내가 필요합니다."
                ),
            )

        return SafetyResult(
            status=SafetyStatus.SAFE,
            message="안전성 검사를 통과했습니다.",
        )

    @staticmethod
    def _has_medication_mismatch(
            patient_context: PatientContext,
            result: RecoveryGuideResult,
    ) -> bool:
        if not patient_context.medications:
            return False

        expected_medication_guide = [
            format_patient_medication(medication)
            for medication
            in patient_context.medications
        ]

        return (
                result.guide_content.medication_guide
                != expected_medication_guide
        )

    @staticmethod
    def _collect_guide_texts(
        result: RecoveryGuideResult,
    ) -> list[str]:
        content = result.guide_content

        return [
            *content.medication_guide,
            *content.patient_instructions,
            *content.public_information,
            *content.lifestyle_guide,
            *content.warning_signs,
            *content.follow_up_schedule,
            content.safety_notice,
        ]

    @classmethod
    def _is_confirmed_instruction(
        cls,
        text: str,
        patient_context: PatientContext,
    ) -> bool:
        normalized_text = cls._normalize_text(text)

        return any(
            cls._normalize_text(
                instruction.content
            )
            == normalized_text
            for instruction
            in patient_context.instructions
        )

    @staticmethod
    def _contains_confirmed_diagnosis(
        text: str,
        patient_context: PatientContext,
    ) -> bool:
        normalized_text = text.lower()

        return any(
            diagnosis.strip().lower()
            in normalized_text
            for diagnosis
            in patient_context.diagnoses
            if diagnosis.strip()
        )

    @staticmethod
    def _matches_any(
        text: str,
        patterns: list[re.Pattern[str]],
    ) -> bool:
        return any(
            pattern.search(text)
            for pattern in patterns
        )

    @staticmethod
    def _has_medical_disclaimer(
        safety_notice: str,
    ) -> bool:
        normalized = safety_notice.strip()

        has_medical_reference = any(
            keyword in normalized
            for keyword in [
                "의료진",
                "의사",
                "진료",
            ]
        )

        return (
            has_medical_reference
            and "대체" in normalized
        )

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return re.sub(
            r"[\s.,!?]",
            "",
            value,
        ).lower()
