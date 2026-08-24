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
    _MEDICATION_CHANGE_ACTION_EXPRESSION = (
        r"(?:"
        r"(?:중단|변경|증량|감량)\s*"
        r"(?:"
        r"하세요|하십시오|해야\s*합니다|"
        r"해도\s*(?:됩니다|돼요)|해\s*주세요|"
        r"하셔도\s*(?:됩니다|돼요)|"
        r"하셔야\s*합니다|하시기\s*바랍니다|"
        r"해\s*주시기\s*바랍니다"
        r")|"
        r"끊\s*"
        r"(?:"
        r"으세요|으십시오|어야\s*합니다|"
        r"어도\s*(?:됩니다|돼요)|어\s*주세요|"
        r"으셔도\s*(?:됩니다|돼요)|"
        r"으셔야\s*합니다|으시기\s*바랍니다"
        r")|"
        r"안\s*먹어도\s*(?:됩니다|돼요)|"
        r"복용\s*하지\s*않아도\s*(?:됩니다|돼요)|"
        r"건너뛰\s*"
        r"(?:"
        r"세요|십시오|어야\s*합니다|"
        r"어도\s*(?:됩니다|돼요)|어\s*주세요|"
        r"셔도\s*(?:됩니다|돼요)|"
        r"셔야\s*합니다|시기\s*바랍니다"
        r")|"
        r"(?:늘리|줄이)\s*"
        r"(?:"
        r"세요|십시오|셔도\s*(?:됩니다|돼요)|"
        r"셔야\s*합니다|시기\s*바랍니다"
        r")|"
        r"(?:늘려|줄여)\s*"
        r"(?:"
        r"야\s*합니다|도\s*(?:됩니다|돼요)|"
        r"주세요|주시기\s*바랍니다"
        r")|"
        r"바꾸\s*"
        r"(?:"
        r"세요|십시오|셔도\s*(?:됩니다|돼요)|"
        r"셔야\s*합니다|시기\s*바랍니다"
        r")|"
        r"바꿔\s*"
        r"(?:"
        r"야\s*합니다|도\s*(?:됩니다|돼요)|"
        r"주세요|주시기\s*바랍니다"
        r")"
        r")"
    )
    _MEDICATION_CHANGE_ACTION_PATTERN = re.compile(
        _MEDICATION_CHANGE_ACTION_EXPRESSION,
        re.IGNORECASE,
    )
    _ANCHORED_MEDICATION_CHANGE_ACTION_PATTERN = re.compile(
        rf"(?:"
        rf"{_MEDICATION_CHANGE_ACTION_EXPRESSION}|"
        rf"하지\s*않아도\s*(?:됩니다|돼요)"
        rf")",
        re.IGNORECASE,
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

        if self._has_medication_change_instruction(
            patient_context=patient_context,
            result=result,
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
    def _has_medication_change_instruction(
        cls,
        patient_context: PatientContext,
        result: ChatAnswerResult,
    ) -> bool:
        normalized_text = cls._normalize_spacing(result.answer)

        if result.intent == ChatIntent.MEDICATION and cls._MEDICATION_CHANGE_ACTION_PATTERN.search(normalized_text):
            return True

        medication_names = {
            medication.name.strip() for medication in patient_context.medications if medication.name.strip()
        }
        if cls._has_cross_sentence_medication_change(
            text=normalized_text,
            medication_names=medication_names,
        ):
            return True

        anchors = {
            "약",
            "복용",
            "복용량",
            "용량",
            "횟수",
            *medication_names,
        }
        anchor_pattern = "|".join(
            re.escape(anchor)
            for anchor in sorted(
                anchors,
                key=len,
                reverse=True,
            )
        )
        medication_change_pattern = re.compile(
            rf"(?:{anchor_pattern})"
            rf"[^.!?。！？]{{0,30}}?"
            rf"{cls._ANCHORED_MEDICATION_CHANGE_ACTION_PATTERN.pattern}",
            re.IGNORECASE,
        )

        return bool(medication_change_pattern.search(normalized_text))

    @classmethod
    def _has_cross_sentence_medication_change(
        cls,
        text: str,
        medication_names: set[str],
    ) -> bool:
        if not medication_names:
            return False

        medication_name_pattern = "|".join(
            re.escape(name)
            for name in sorted(
                medication_names,
                key=len,
                reverse=True,
            )
        )
        cross_sentence_pattern = re.compile(
            rf"(?:{medication_name_pattern})"
            rf"[^.!?。！？]{{0,80}}[.!?。！？]\s*"
            rf"(?:[-•]\s*)?"
            rf"(?:"
            rf"내일부터|오늘부터|지금부터|앞으로|"
            rf"이제부터|다음부터"
            rf")?\s*"
            rf"{cls._MEDICATION_CHANGE_ACTION_PATTERN.pattern}",
            re.IGNORECASE,
        )

        return bool(cross_sentence_pattern.search(text))

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
