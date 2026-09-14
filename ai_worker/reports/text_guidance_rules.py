"""Source-text presentation rules, not a clinical risk or interaction classifier."""

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TextGuidanceRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contraindication_phrases: tuple[str, ...] = Field(min_length=1)
    driving_mentions: tuple[str, ...] = Field(min_length=1)
    food_drink_mentions: tuple[str, ...] = Field(min_length=1)
    food_drink_nonmatches: tuple[str, ...]
    food_drink_mixed_contexts: tuple[str, ...] = Field(min_length=1)

    @field_validator("*")
    @classmethod
    def validate_terms(cls, terms: tuple[str, ...]) -> tuple[str, ...]:
        if any(not term.strip() or re.search(r"\s", term) for term in terms) or len(set(terms)) != len(terms):
            raise ValueError("Source matching terms must be nonempty, compact, and unique")
        return terms


@lru_cache(maxsize=1)
def load_text_guidance_rules() -> TextGuidanceRules:
    return TextGuidanceRules.model_validate_json(
        (Path(__file__).parent / "data" / "text_guidance_rules.json").read_text(encoding="utf-8")
    )


def mentions_food_or_drink(text: str) -> bool:
    rules = load_text_guidance_rules()
    compact = re.sub(r"\s+", "", text)
    for nonmatch in rules.food_drink_nonmatches:
        compact = compact.replace(nonmatch, "")
    return any(term in compact for term in rules.food_drink_mentions)


def is_standalone_food_or_drink_guidance(text: str) -> bool:
    """Conservatively omit mixed medication contexts from food-only cards.

    This is a presentation guard, not exhaustive drug-name recognition. The
    caller must preserve the full source in the general interaction card;
    removing medication clauses could change the warning's conditions.
    """
    if not mentions_food_or_drink(text):
        return False
    compact = re.sub(r"\s+", "", text)
    return not any(marker in compact for marker in load_text_guidance_rules().food_drink_mixed_contexts)
