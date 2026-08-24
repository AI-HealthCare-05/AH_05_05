import re

from ai_worker.schemas.chat import (
    ChatInputRiskResult,
)
from ai_worker.schemas.enums import ChatRiskLevel


class RuleBasedChatInputRiskClassifier:
    _RULES: tuple[
        tuple[
            str,
            tuple[re.Pattern[str], ...],
        ],
        ...,
    ] = (
        (
            "MEDICATION_CHANGE_REQUEST",
            (
                re.compile(
                    r"(?:"
                    r"약|복용(?:량)?|용량|횟수|"
                    r"아스피린"
                    r")"
                    r".{0,20}"
                    r"(?:"
                    r"중단|끊|안\s*먹|건너뛰|"
                    r"늘리|늘려|증량|"
                    r"줄이|줄여|감량|"
                    r"변경|바꾸|바꿔"
                    r")"
                ),
            ),
        ),
        (
            "DIAGNOSIS_REQUEST",
            (
                re.compile(
                    r"(?:"
                    r"진단(?:해|해주세요|해줘|해\s*줘)|"
                    r"무슨\s*(?:병|질환)|"
                    r"(?:병|질환)(?:인지|인가)"
                    r")"
                ),
            ),
        ),
        (
            "TREATMENT_DECISION_REQUEST",
            (
                re.compile(
                    r"(?:수술|시술|입원|치료)"
                    r".{0,25}"
                    r"(?:"
                    r"해야|받아야|필요한지|결정"
                    r")"
                ),
            ),
        ),
        (
            "EMERGENCY_SYMPTOM",
            (
                re.compile(
                    r"(?:"
                    r"가슴(?:이|에)?\s*"
                    r"(?:너무\s*)?"
                    r"(?:아프|통증)|"
                    r"흉통|"
                    r"숨(?:을)?\s*"
                    r"쉬(?:기|기가)?\s*"
                    r"(?:힘들|어렵)|"
                    r"호흡\s*곤란|"
                    r"의식(?:을)?\s*(?:잃|없)|"
                    r"갑자기.{0,10}"
                    r"(?:마비|말이\s*안)"
                    r")"
                ),
            ),
        ),
    )

    def assess(
        self,
        question: str,
    ) -> ChatInputRiskResult:
        normalized_question = question.strip()

        if not normalized_question:
            raise ValueError("검사할 질문은 비어 있을 수 없습니다.")

        reason_codes = [
            reason_code
            for reason_code, patterns in self._RULES
            if self._matches_any(
                question=normalized_question,
                patterns=patterns,
            )
        ]

        risk_level = ChatRiskLevel.HIGH if reason_codes else ChatRiskLevel.LOW

        return ChatInputRiskResult(
            risk_level=risk_level,
            reason_codes=reason_codes,
        )

    @staticmethod
    def _matches_any(
        question: str,
        patterns: tuple[re.Pattern[str], ...],
    ) -> bool:
        return any(pattern.search(question) for pattern in patterns)
