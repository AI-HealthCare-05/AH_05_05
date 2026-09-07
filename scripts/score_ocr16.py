"""Score source-readable fields; missing extraction counts as incorrect, not excluded."""

import json
import re
import statistics
import unicodedata
from decimal import Decimal, InvalidOperation

from scripts.benchmark_ocr16 import OUTPUT, VERSIONS, digest, prepare
from scripts.compare_ocr_random8 import save

FIELDS = ("name", "strength", "doseQuantity", "timesPerDay", "days")


def name_key(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    for old, new in (("밀리그램", "mg"), ("마이크로그램", "ug"), ("밀리리터", "ml"), ("그램", "g"), ("퍼센트", "%")):
        text = text.replace(old, new)
    # Parenthetical ingredient prose is not a product name. Keep numeric pack/strength.
    text = re.sub(r"\(([^)]*)\)", lambda m: m[1] if re.fullmatch(r"[\d\s./%a-z+-]+", m[1]) else "", text)
    return re.sub(r"[\s_(),\[\]]", "", text)


def number_key(value):
    if value is None:
        return None
    value = re.sub(r"\s*(정|캡슐|포|ml|mL)$", "", str(value).strip())
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def strength_key(value):
    text = name_key(value)
    text = re.sub(r"/(?:1)?(?:정|캡슐|포)$", "", text)
    match = re.fullmatch(r"(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)*)\s*(mg|ug|g|ml|%)", text)
    if not match:
        return text
    values, unit = match.groups()
    factor = {"g": Decimal(1000), "mg": Decimal(1), "ug": Decimal("0.001")}.get(unit, Decimal(1))
    return ("mg" if unit in {"g", "mg", "ug"} else unit, tuple(Decimal(v) * factor for v in values.split("/")))


def row_mapping(run, expected, predicted):
    if not predicted:
        return [None] * len(expected)
    if run["id"] == "sample-16" and run["version"] == "v3.2.7":
        # Explicit source-row audit: only rows 2, 4, 5 survived in this output.
        assert len(expected) == 6 and len(predicted) == 3
        return [None, 0, None, 1, 2, None]
    assert len(expected) == len(predicted), (run["id"], len(expected), len(predicted))
    return list(range(len(expected)))


def main():
    manifest = prepare()
    truth = []
    for name in ("truth-01-04.json", "truth-05-08.json", "truth-09-12.json", "truth-13-16.json"):
        truth.extend(json.loads((OUTPUT / name).read_text(encoding="utf-8"))["samples"])
    assert [t["id"] for t in truth] == [e["id"] for e in manifest["images"]]
    assert all(all(f in row for f in FIELDS) for t in truth for row in t["rows"]), "Incomplete truth audit"
    results = json.loads((OUTPUT / "results.json").read_text(encoding="utf-8"))
    timings = json.loads((OUTPUT / "local-timings.json").read_text(encoding="utf-8"))
    assert len(results) == 48 and timings["identity"] == digest(manifest)
    assert all(r["identity"] == digest(manifest) for r in results)
    save(
        OUTPUT / "ground-truth.json",
        {
            "method": "blind visual transcription plus independent source audit",
            "samples": truth,
            "checksum": digest(truth),
        },
    )
    details = []
    for run in results:
        expected = next(t for t in truth if t["id"] == run["id"])["rows"]
        predicted = run["review"]["medications"]
        mapping = row_mapping(run, expected, predicted)
        cells = []
        full_rows = []
        for row_index, (gold, pred_index) in enumerate(zip(expected, mapping, strict=True)):
            pred = {} if pred_index is None else predicted[pred_index]
            row_cells = []
            for field in FIELDS:
                if gold.get(field) is None or (field == "name" and not gold["nameAssessable"]):
                    continue
                norm = {"name": name_key, "strength": strength_key}.get(field, number_key)
                assert norm(gold[field]) is not None, (run["id"], row_index, field)
                correct = pred.get(field) is not None and norm(gold[field]) == norm(pred[field])
                cell = {
                    "row": row_index + 1,
                    "predIndex": pred_index,
                    "field": field,
                    "expected": gold[field],
                    "actual": pred.get(field),
                    "correct": correct,
                }
                cells.append(cell)
                row_cells.append(cell)
            if len(row_cells) == len(FIELDS):
                full_rows.append(all(c["correct"] for c in row_cells))
        details.append(
            {
                "id": run["id"],
                "version": run["version"],
                "expectedRows": len(expected),
                "extractedRows": len(predicted),
                "cells": cells,
                "fullRows": full_rows,
            }
        )
    summaries = {}
    for label, ids in (
        ("all16", {e["id"] for e in manifest["images"]}),
        ("original8", {e["id"] for e in manifest["images"][:8]}),
        ("additional8", {e["id"] for e in manifest["images"][8:]}),
    ):
        summary = []
        for version in VERSIONS:
            runs = [r for r in results if r["version"] == version and r["id"] in ids]
            scores = [r for r in details if r["version"] == version and r["id"] in ids]
            cells = [c for s in scores for c in s["cells"]]
            full = [v for s in scores for v in s["fullRows"]]
            field_scores = {
                f: {
                    "correct": sum(c["correct"] for c in cells if c["field"] == f),
                    "total": sum(c["field"] == f for c in cells),
                }
                for f in FIELDS
            }
            local = [statistics.median(r["times"][version]) for r in timings["runs"] if r["id"] in ids]
            summary.append(
                {
                    "version": version,
                    "images": len(ids),
                    "preprocessMeanOfMediansMs": statistics.mean(local),
                    "wallMeanMs": statistics.mean(r["wallMs"] for r in runs),
                    "wallMedianMs": statistics.median(r["wallMs"] for r in runs),
                    "ocrMeanCalledMs": statistics.mean(
                        s["elapsedMs"] for r in runs for s in r["stages"] if s["name"] == "ocr" and s["callCount"]
                    ),
                    "ocrCalls": sum(s["callCount"] for r in runs for s in r["stages"] if s["name"] == "ocr"),
                    "llmCalls": sum(s["callCount"] for r in runs for s in r["stages"] if s["name"] == "llm"),
                    "nonemptyImages": sum(bool(r["review"]["medications"]) for r in runs),
                    "recaptureImages": sum(r["recapture"] for r in runs),
                    "extractedRows": sum(s["extractedRows"] for s in scores),
                    "expectedRows": sum(s["expectedRows"] for s in scores),
                    "correctFields": sum(c["correct"] for c in cells),
                    "assessableFields": len(cells),
                    "fields": field_scores,
                    "fullRowsCorrect": sum(full),
                    "fullRowsAssessable": len(full),
                }
            )
        summaries[label] = summary
    save(
        OUTPUT / "scores.json",
        {"identity": digest(manifest), "truthChecksum": digest(truth), "summaries": summaries, "details": details},
    )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
