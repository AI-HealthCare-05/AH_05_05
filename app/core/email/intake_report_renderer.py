"""Email-only projection of the already generated web cards; no AI or new analysis."""

import html
import math
import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from app.dtos.intake_reports import IntakeReportResponse

_TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parents[2] / "static" / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)
_TEMPLATES.filters["evidence"] = html.unescape
_EVIDENCE_LABELS = {
    "APPROVED_RULE": "승인된 규칙",
    "PUBLIC_GUIDE": "공개 안내",
    "RESEARCH": "연구 근거",
    "REGISTERED_INTAKE": "등록한 복용 정보",
    "UNVERIFIED": "확인되지 않은 정보",
}


def _number(value: str | None) -> Decimal | None:
    try:
        parsed = Decimal(value) if value and value.strip() else None
    except InvalidOperation:
        return None
    if parsed is None or not parsed.is_finite() or parsed < 0 or not math.isfinite(float(parsed)):
        return None
    # Match the web's finite-number boundary without expanding arbitrary exponents.
    return parsed if float(parsed) != 0 else Decimal(0)


def _format_number(value: Decimal) -> str:
    text = format(value, ",f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _intake(value: str) -> str:
    # Only the registered dose's first number; never edit clinical instructions.
    return re.sub(
        r"^\s*(\d+\.\d+)(?=$|\s|정|캡슐|포|mg|ml|mL|g)",
        lambda match: match[1].rstrip("0").rstrip("."),
        value,
    )


def _safe_url(value: str | None) -> str | None:
    try:
        url = urlsplit(value or "")
        if url.scheme in {"https", "http"} and url.netloc and url.username is None and url.password is None:
            return value
    except ValueError:
        pass
    return None


def _groups(cards: list[dict[str, Any]], context_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    indexes: dict[tuple[str, ...], int] = {}
    for card in cards:
        action = " ".join(html.unescape(card.get("action") or "").split())
        key = (*[card.get(field) or "" for field in context_fields], action)
        if action and key in indexes:
            groups[indexes[key]]["cards"].append(card)
        else:
            if action:
                indexes[key] = len(groups)
            groups.append({"action": action, "cards": [card]})
    return groups


def _nutrient(item: dict[str, Any]) -> dict[str, Any]:
    amount, reference, upper = (_number(item.get(key)) for key in ("amount", "reference_value", "upper_limit_value"))
    reference = reference or None
    upper = upper if upper and (reference is None or upper >= reference) else None
    scale = upper or reference
    comparable = amount is not None and scale is not None and bool(item.get("unit"))
    result = {
        **item,
        "display_amount": _format_number(amount) if amount is not None else "미확인",
        "reference_label": {"RNI": "권장", "AI": "충분"}.get(item.get("reference_kind") or "", "기준"),
        "display_reference": _format_number(reference) if reference else None,
        "display_upper": _format_number(upper) if upper else None,
        "over_upper": upper is not None and amount is not None and amount > upper,
        "comparable": comparable,
        "unknown": amount is None,
        "segments": [],
    }
    if comparable:
        assert amount is not None and scale is not None

        def position(value: Decimal) -> float:
            return float(min(Decimal(100), value / scale * 80))

        fill = position(amount)
        ticks = {position(reference)} if reference else set()
        if upper:
            ticks.add(80.0)
        boundaries = sorted({0.0, 100.0, fill, *ticks})
        result["segments"] = [
            {"width": round(right - left, 6), "filled": right <= fill, "tick": right in ticks, "current": right == fill}
            for left, right in zip(boundaries, boundaries[1:], strict=False)
            if right > left
        ]
        result["fill"] = fill
        result["range_label"] = f"{item['nutrient_name']} 합계 {_format_number(amount)}{item['unit']}"
    return result


class _EmailText(HTMLParser):
    """Derive the text alternative from the same template, without a second entity decode."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored = 0
        self.link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"head", "style"}:
            self.ignored += 1
        if self.ignored:
            return
        if tag in {"h1", "h2", "h3", "p", "tr", "li", "br"}:
            self.parts.append("\n")
        if tag == "a":
            self.link = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"head", "style"}:
            self.ignored = max(0, self.ignored - 1)
        if self.ignored:
            return
        if tag == "a" and self.link:
            self.parts.append(f" ({self.link})")
            self.link = None
        if tag in {"h1", "h2", "h3", "p", "tr", "li", "td", "div"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line for part in "".join(self.parts).splitlines() if (line := " ".join(part.split())))


def render_intake_report_email(report: "IntakeReportResponse") -> tuple[str, str] | None:
    if report.presentation_version != "ai-report-v11" or report.cards is None:
        return None
    data = report.model_dump(mode="json")
    cards = data["cards"]
    stack = data["current_stack"]
    for item in stack:
        item["registered_intake_info"] = _intake(item["registered_intake_info"])
    medications = [item for item in stack if item["item_type"] == "MEDICATION"]
    supplements = [item for item in stack if item["item_type"] == "SUPPLEMENT"]
    registered = {item["item_id"]: item["registered_intake_info"] for item in medications}
    for card in cards["medications"]:
        card["registered_intake"] = registered.get(card["item_id"])
        for detail in card["details"]:
            if re.search(r"등록.*복용|복용.*등록", detail["label"]):
                card["registered_intake"] = None
                detail["label"] = "사용자가 등록한 복용 정보"
                detail["text"] = _intake(detail["text"])
    for card in cards["interactions"]:
        card["label"] = (
            "공개 안내 · 개인 조합 확인 필요"
            if card["evidence_level"] == "PUBLIC_GUIDE"
            else {"WARNING": "중요 주의", "CHECK": "복용 전 상담", "INFORMATION": "확인할 점"}[card["action_level"]]
        )
    for source in cards["sources"]:
        source["safe_url"] = _safe_url(source.get("url"))
        source["evidence_label"] = _EVIDENCE_LABELS.get(source["evidence_level"], "근거 수준 미확인")
    nutrients = [_nutrient(item) for item in data["nutrient_totals"] if _number(item.get("amount")) != 0]
    markup = _TEMPLATES.get_template("emails/intake_report_cards.html").render(
        report=data,
        cards=cards,
        medications=medications,
        supplements=supplements,
        nutrients=nutrients,
        interactions=_groups(
            sorted(cards["interactions"], key=lambda card: card["action_level"] != "WARNING"),
            ("evidence_level", "action_level"),
        ),
        overlaps=_groups(cards["overlaps"], ()),
        lifestyle=_groups(cards["lifestyle"], ("category",)),
    )
    return markup, intake_report_plain_text(markup)


def intake_report_plain_text(markup: str) -> str:
    plain = _EmailText()
    plain.feed(markup)
    return plain.text()
