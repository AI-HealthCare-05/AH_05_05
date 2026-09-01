import re
import unicodedata

from ai_worker.schemas.medication_search import SupplementIngredientFamily

_INGREDIENT_FAMILIES = (
    SupplementIngredientFamily(
        canonical_name="비타민 B",
        member_names=[
            "비타민 B1(티아민)",
            "비타민 B2(리보플라빈)",
            "비타민 B3(나이아신)",
            "비타민 B5(판토텐산)",
            "비타민 B6(피리독신)",
            "비타민 B7(비오틴)",
            "비타민 B9(엽산)",
            "비타민 B12(코발라민)",
        ],
        search_names=[
            "비타민 B1",
            "비타민 B2",
            "비타민 B3",
            "비타민 B5",
            "비타민 B6",
            "비타민 B7",
            "비타민 B9",
            "비타민 B12",
        ],
        search_terms=[
            "비타민 B군",
            "비타민 B 복합체",
            "vitamin B complex",
        ],
    ),
)

_FAMILY_ALIASES = {
    "비타민 B": (
        "비타민 b",
        "비타민 b군",
        "비타민 b 복합체",
        "vitamin b",
        "vitamin b complex",
    ),
}


def find_supplement_ingredient_family(
    value: str,
) -> SupplementIngredientFamily | None:
    normalized = _normalize(value)
    for family in _INGREDIENT_FAMILIES:
        aliases = _FAMILY_ALIASES[family.canonical_name]
        if normalized in {_normalize(alias) for alias in aliases}:
            return family
    return None


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()
