import re
import unicodedata
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from ai_worker.schemas.intake_report import IntakeReportDraft


class IntakeReportGroundingValidator:
    """Restrict report Markdown to grounded, non-prescriptive wording."""

    _RAW_HTML_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")
    _DOSAGE_TOKEN_PATTERN = re.compile(
        r"(?<![\d.,])[+-]?(?:\d+(?:[.,]\d*)*|[.,]\d+)(?:e[+-]?\d+)?"
        r"\s*(?:mg|mcg|μg|µg|㎍|g|mL|ml|정|캡슐|포|회|일|시간|%)",
        re.IGNORECASE,
    )
    _MEDICATION_CHANGE_PATTERN = re.compile(
        r"(?:시작|중단|증량|감량|늘리|줄이|변경|건너뛰)"
        r"[^.!?。！？]{0,16}"
        r"(?:세요|십시오|해야\s*합니다|해도\s*됩니다|해\s*주세요)",
        re.IGNORECASE,
    )
    _NEGATED_CHANGE_GUIDANCE_PATTERN = re.compile(
        r"(?:(?:시작|중단|증량|감량|변경|건너뛰)(?:을|를)?\s*하지|"
        r"(?:늘리|줄이)지)\s*마(?:세요|십시오)",
        re.IGNORECASE,
    )
    _EXPERT_CONFIRMATION_PATTERN = re.compile(
        r"(?:시작|중단|증량|감량|변경|건너뛰|늘리기|줄이기)"
        r"\s*(?:은|는|을|를|여부는)?\s*"
        r"(?:전문가|의사|약사|의료진)(?:에게|와|과)?"
        r"[^.!?。！？\n]{0,12}(?:확인|상의|상담)"
        r"[^.!?。！？\n]{0,4}(?:세요|십시오|주세요)",
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
    _PROMPT_INJECTION_PATTERN = re.compile(
        r"(?:이전|앞선)\s*(?:지시|명령)[^.!?\n]{0,20}(?:무시|따르지)|"
        r"(?:시스템|개발자|내부)\s*프롬프트|"
        r"(?:system|developer)\s+(?:prompt|message)|"
        r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
        re.IGNORECASE,
    )
    _URL_PATTERN = re.compile(r"https?://[^\s<>()\]]+", re.IGNORECASE)
    _MARKDOWN_ESCAPE_PATTERN = re.compile(r"\\([\\`*{}\[\]()#+\-.!_|>])")

    def validate(
        self,
        *,
        generated_markdown: str,
        draft: IntakeReportDraft,
    ) -> str | None:
        return (
            None
            if self.validation_issues(generated_markdown=generated_markdown, draft=draft)
            else generated_markdown.strip()
        )

    def validation_issues(self, *, generated_markdown: str, draft: IntakeReportDraft) -> list[dict[str, str]]:
        """Repair feedback stays in the request; log codes only, never source text."""
        normalized = generated_markdown.strip()
        if not normalized:
            return [{"code": "EMPTY_REPORT", "instruction": "v11 보고서 전체 본문을 작성하세요."}]
        checks = (
            (self._has_allowed_headings(normalized), "INVALID_FORMAT", "제목은 #, ##, ###만 사용하세요."),
            (
                not self._has_forbidden_content(normalized),
                "UNSAFE_CONTENT",
                "HTML·코드·명령문과 진단·복용변경 지시·안전 단정을 제거하세요. 원문 경고의 대상과 조건은 보존하세요.",
            ),
            (
                self._urls_are_grounded(generated_markdown=normalized, draft=draft),
                "UNGROUNDED_URLS",
                "입력의 url/source_url에 없는 링크는 제거하세요.",
            ),
            (
                self._dosages_are_grounded(generated_markdown=normalized, draft=draft),
                "UNGROUNDED_NUMBERS",
                "입력에 없는 수치·단위를 제거하거나 해당 근거의 값으로 바로잡으세요. 수치를 다른 제품에 옮기지 마세요.",
            ),
            (
                self._includes_all_registered_items(generated_markdown=normalized, draft=draft),
                "MISSING_PRODUCTS",
                "current_stack의 모든 product_name을 원래 표기 그대로 포함하세요. 정식 명칭이 확인되어도 등록명을 함께 표시하고 추측으로 교정하지 마세요.",
            ),
        )
        return [{"code": code, "instruction": instruction} for passed, code, instruction in checks if not passed]

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
    def _has_forbidden_content(cls, markdown: str) -> bool:
        return bool(
            "```" in markdown
            or cls._RAW_HTML_PATTERN.search(markdown)
            or cls._contains_unsafe_medication_change(markdown)
            or cls._DIAGNOSIS_OR_TREATMENT_PATTERN.search(markdown)
            or cls._UNSUPPORTED_SAFETY_PATTERN.search(markdown)
            or cls._PROMPT_INJECTION_PATTERN.search(markdown)
        )

    @classmethod
    def _contains_unsafe_medication_change(cls, markdown: str) -> bool:
        without_negative_guidance = cls._NEGATED_CHANGE_GUIDANCE_PATTERN.sub("", markdown)
        without_safe_guidance = cls._EXPERT_CONFIRMATION_PATTERN.sub("", without_negative_guidance)
        return cls._MEDICATION_CHANGE_PATTERN.search(without_safe_guidance) is not None

    @classmethod
    def _dosages_are_grounded(
        cls,
        *,
        generated_markdown: str,
        draft: IntakeReportDraft,
    ) -> bool:
        def normalize(token: str) -> tuple[Decimal, str] | None:
            token = unicodedata.normalize("NFKC", token).casefold()
            match = re.fullmatch(r"([+-]?[\d.,]+(?:e[+-]?\d+)?)\s*(.+)", token)
            assert match is not None
            if re.fullmatch(r"[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?|\.\d+)", match[1]) is None:
                return None
            unit = match[2]
            return Decimal(match[1].replace(",", "")), {"mcg": "μg", "µg": "μg"}.get(unit, unit)

        evidence_text = "\n".join(cls._iter_text_values(draft.model_dump(mode="json")))
        nutrient_fragments: list[str] = []
        for total in draft.nutrient_totals:
            if total.amount is not None and total.unit is not None:
                nutrient_fragments.append(f"{total.amount} {total.unit}")
            if total.reference_value is not None and total.unit is not None:
                nutrient_fragments.append(f"{total.reference_value} {total.unit}")
            if total.reference_percent is not None:
                nutrient_fragments.append(f"{total.reference_percent}%")
        grounded_text = "\n".join((evidence_text, *nutrient_fragments))
        draft_tokens = {normalize(token) for token in cls._DOSAGE_TOKEN_PATTERN.findall(grounded_text)}
        generated_tokens = {normalize(token) for token in cls._DOSAGE_TOKEN_PATTERN.findall(generated_markdown)}
        return None not in generated_tokens and generated_tokens.issubset(draft_tokens)

    @classmethod
    def _urls_are_grounded(
        cls,
        *,
        generated_markdown: str,
        draft: IntakeReportDraft,
    ) -> bool:
        generated_urls = {cls._normalize_url(url) for url in cls._URL_PATTERN.findall(generated_markdown)}
        if not generated_urls:
            return True
        evidence_payload = draft.model_dump(mode="json")
        allowed_urls = {cls._normalize_url(value) for value in cls._iter_url_fields(evidence_payload)}
        return generated_urls.issubset(allowed_urls)

    @classmethod
    def _includes_all_registered_items(
        cls,
        *,
        generated_markdown: str,
        draft: IntakeReportDraft,
    ) -> bool:
        normalized_markdown = cls._normalize_markdown_text(generated_markdown)
        registered_item_names = (item.product_name for item in draft.current_stack)
        return all(cls._normalize_markdown_text(name) in normalized_markdown for name in registered_item_names)

    @classmethod
    def _normalize_markdown_text(cls, value: str) -> str:
        unescaped = cls._MARKDOWN_ESCAPE_PATTERN.sub(r"\1", value)
        normalized = unicodedata.normalize("NFKC", unescaped).casefold()
        return re.sub(r"\s+", "", normalized)

    @staticmethod
    def _normalize_url(value: str) -> str:
        return value.rstrip(".,;:!?'")

    @classmethod
    def _iter_text_values(cls, value: Any) -> Iterator[str]:
        if isinstance(value, str):
            yield value
            return
        if isinstance(value, dict):
            for nested in value.values():
                yield from cls._iter_text_values(nested)
            return
        if isinstance(value, list):
            for nested in value:
                yield from cls._iter_text_values(nested)

    @classmethod
    def _iter_url_fields(cls, value: Any) -> Iterator[str]:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {"url", "source_url"} and isinstance(nested, str):
                    yield nested
                else:
                    yield from cls._iter_url_fields(nested)
            return
        if isinstance(value, list):
            for nested in value:
                yield from cls._iter_url_fields(nested)
