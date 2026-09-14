"""Exercise generic display variations against every versioned guide, not a drug allowlist."""

import gzip
import json
import re
from pathlib import Path

from ai_worker.repositories.report_medication_guide_repository import ReportMedicationGuideRepository


def test_every_seed_product_keeps_identity_under_display_only_variations():
    seed = Path(__file__).resolve().parents[3] / "data/reference_seed/v1/medication_product_guides.jsonl.gz"
    with gzip.open(seed, "rt", encoding="utf-8") as source:
        names = [json.loads(line)["product_name"] for line in source if line.strip()]
    assert names
    fullwidth = str.maketrans({chr(code): chr(code + 0xFEE0) for code in range(33, 127)})
    count = 0
    strength_cases = 0
    for name in names:
        # Input variations are generated independently of the production normalizer.
        variants = [name, " ".join(name), name.translate(fullwidth)]
        head, bracket, annotations = name.partition("(")
        ascii_units = head.replace("밀리그램", "mg").replace("밀리그람", "mg")
        if ascii_units != head:
            variants.append(ascii_units + bracket + annotations)
        scaled = re.sub(
            r"([0-9]+(?:\.[0-9]+)?)(?=mg|밀리그램|밀리그람|마이크로그램)",
            lambda match: match[1] + ("00" if "." in match[1] else ".00"),
            head,
        )
        if scaled != head:
            variants.append(scaled + bracket + annotations)
            strength_cases += 1
            changed_strength = re.sub(
                r"([0-9]+(?:\.[0-9]+)?)(?=mg|밀리그램|밀리그람|마이크로그램)",
                lambda match: match[1] + "9",
                head,
                count=1,
            )
            assert not ReportMedicationGuideRepository._matches_product_name(
                changed_strength + bracket + annotations, name
            ), name
        for variant in variants:
            assert ReportMedicationGuideRepository._matches_product_name(variant, name), (variant, name)
            count += 1
    assert strength_cases > 0
    print(f"catalog_products={len(names)} display_variations={count} numeric_variation_products={strength_cases}")
