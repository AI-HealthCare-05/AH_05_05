import re

from ai_worker.schemas.intake_report import IntakeReportDraft


class IntakeReportGroundingValidator:
    """Restrict report Markdown to grounded, non-prescriptive wording."""

    _RAW_HTML_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")
    _DOSAGE_TOKEN_PATTERN = re.compile(
        r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|μg|㎍|g|mL|ml|정|캡슐|포|회|일|시간|%)",
        re.IGNORECASE,
    )
    _MEDICATION_CHANGE_PATTERN = re.compile(
        r"(?:시작|중단|증량|감량|늘리|줄이|변경|건너뛰)"
        r"[^.!?。！？]{0,16}"
        r"(?:세요|십시오|해야\s*합니다|해도\s*됩니다|해\s*주세요)",
        re.IGNORECASE,
    )
    _DIAGNOSIS_OR_TREATMENT_PATTERN = re.compile(
        r"(?:진단됩니다|판단됩니다|처방합니다|치료가\s*필요합니다|"
        r"수술이\s*필요합니다)",
        re.IGNORECASE,
    )
    _UNSUPPORTED_SAFETY_PATTERN = re.compile(
        r"(?:안전합니다|문제\s*없습니다|괜찮습니다|"
        r"상호작용이\s*없습니다|부작용이\s*없습니다)",
        re.IGNORECASE,
    )

    def validate(
        self,
        *,
        generated_markdown: str,
        draft: IntakeReportDraft,
    ) -> str | None:
        normalized = generated_markdown.strip()
        if not normalized:
            return None
        if "```" in normalized or self._RAW_HTML_PATTERN.search(normalized):
            return None
        if not self._has_allowed_headings(normalized):
            return None
        if self._MEDICATION_CHANGE_PATTERN.search(normalized):
            return None
        if self._DIAGNOSIS_OR_TREATMENT_PATTERN.search(normalized):
            return None
        if self._UNSUPPORTED_SAFETY_PATTERN.search(normalized) and not self._UNSUPPORTED_SAFETY_PATTERN.search(
            draft.deterministic_markdown,
        ):
            return None
        if not self._dosages_are_grounded(
            generated_markdown=normalized,
            draft_markdown=draft.deterministic_markdown,
        ):
            return None
        return normalized

    @staticmethod
    def _has_allowed_headings(markdown: str) -> bool:
        for line in markdown.splitlines():
            stripped = line.lstrip()
            if not stripped.startswith("#"):
                continue
            match = re.match(r"^(#{1,3})\s+", stripped)
            if match is None:
                return False
        return True

    @classmethod
    def _dosages_are_grounded(
        cls,
        *,
        generated_markdown: str,
        draft_markdown: str,
    ) -> bool:
        def normalize(token: str) -> str:
            return token.casefold().replace(" ", "")

        draft_tokens = {normalize(token) for token in cls._DOSAGE_TOKEN_PATTERN.findall(draft_markdown)}
        generated_tokens = {normalize(token) for token in cls._DOSAGE_TOKEN_PATTERN.findall(generated_markdown)}
        return generated_tokens.issubset(draft_tokens)
