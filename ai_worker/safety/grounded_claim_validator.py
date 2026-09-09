import hashlib
import re

from ai_worker.llm.assemblers.medication_answer_assembler import (
    MEDICAL_DISCLAIMER,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    GroundedClaimValidationDiagnostic,
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
    _MEDICATION_CHANGE_ACTIONS = (
        (re.compile(r"중단|끊|건너뛰"), "STOP"),
        (re.compile(r"시작"), "START"),
        (re.compile(r"증량|늘리"), "INCREASE"),
        (re.compile(r"감량|줄이"), "DECREASE"),
        (re.compile(r"변경"), "CHANGE"),
    )
    _MEDICATION_CHANGE_TARGETS = (
        (re.compile(r"복용량|용량"), "DOSAGE"),
        (re.compile(r"횟수"), "FREQUENCY"),
        (re.compile(r"처방"), "PRESCRIPTION"),
        (re.compile(r"약"), "MEDICATION"),
        (re.compile(r"복용"), "ADMINISTRATION"),
    )

    def diagnose(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> GroundedClaimValidationDiagnostic:
        del context
        normalized_answer = self._normalize_spacing(result.answer)
        if match := self._MEDICATION_CHANGE_PATTERN.search(normalized_answer):
            if self._matches_official_warning(
                match_text=match.group(),
                official_warning_texts=result.official_warning_texts,
            ):
                return GroundedClaimValidationDiagnostic(
                    official_warning_allowed=True,
                )
            return self._match_diagnostic(
                rule_code="MEDICATION_CHANGE_INSTRUCTION",
                match_text=match.group(),
                action=self._match_category(match.group(), self._MEDICATION_CHANGE_ACTIONS),
                target=self._match_category(match.group(), self._MEDICATION_CHANGE_TARGETS),
            )
        if match := self._DIAGNOSIS_PATTERN.search(normalized_answer):
            return self._match_diagnostic(
                rule_code="DIAGNOSTIC_ASSERTION",
                match_text=match.group(),
            )
        if match := self._TREATMENT_PATTERN.search(normalized_answer):
            return self._match_diagnostic(
                rule_code="TREATMENT_DECISION",
                match_text=match.group(),
            )
        return GroundedClaimValidationDiagnostic(
            disclaimer_added=not self._has_disclaimer(normalized_answer),
        )

    async def validate(
        self,
        *,
        context: ActiveIntakeContext,
        result: MedicationChatResult,
    ) -> MedicationChatResult:
        diagnostic = self.diagnose(context=context, result=result)
        if diagnostic.rule_code is not None:
            return self._blocked_result(
                result,
                reason_code=diagnostic.rule_code,
            )
        if diagnostic.disclaimer_added:
            return result.model_copy(
                update={
                    "answer": f"{result.answer.rstrip()}\n\n{MEDICAL_DISCLAIMER}",
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
    def _match_category(
        value: str,
        categories: tuple[tuple[re.Pattern[str], str], ...],
    ) -> str | None:
        return next(
            (category for pattern, category in categories if pattern.search(value)),
            None,
        )

    @staticmethod
    def _match_diagnostic(
        *,
        rule_code: str,
        match_text: str,
        action: str | None = None,
        target: str | None = None,
    ) -> GroundedClaimValidationDiagnostic:
        return GroundedClaimValidationDiagnostic(
            rule_code=rule_code,
            matched_action=action,
            matched_target=target,
            matched_fragment_hash=hashlib.sha256(
                match_text.encode("utf-8"),
            ).hexdigest(),
        )

    @staticmethod
    def _normalize_spacing(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def _matches_official_warning(
        cls,
        *,
        match_text: str,
        official_warning_texts: list[str],
    ) -> bool:
        normalized_match = cls._comparison_key(match_text)
        return bool(normalized_match) and any(
            normalized_match in cls._comparison_key(warning) for warning in official_warning_texts
        )

    @staticmethod
    def _comparison_key(value: str) -> str:
        return re.sub(r"\s+", "", value).casefold()
