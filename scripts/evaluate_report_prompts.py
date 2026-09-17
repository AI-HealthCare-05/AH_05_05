"""Opt-in synthetic prompt evaluation, without patient data, DB or vector writes."""

import argparse
import asyncio
import json
import time

from ai_worker.core.config import Config
from ai_worker.reports.report_rag_pipeline import _invoke, build_openai_report_rag_pipeline


async def run():
    settings = Config()
    pipeline = build_openai_report_rag_pipeline(
        retriever=None,
        dataset_version=settings.KNOWLEDGE_DATASET_VERSION,
        model=settings.OPENAI_CHAT_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )
    quote = "가상성분A는 조건X에 해당할 때 음료Y와 함께 먹지 않도록 주의해야 합니다."
    target = {"id": "supplement:1", "name": "가상성분A", "aliases": []}
    other = {"id": "medication:1", "name": "가상제품B", "aliases": []}
    trusted = {
        "plan": [{"section_id": "food_drink", "target_ids": [target["id"], other["id"]]}],
        "targets": [target, other],
        "approved_warnings": [],
        "chunks": [{"chunk_id": "synthetic-a", "content": quote, "source": "가상 시험 문서"}],
    }
    good = {
        "section_id": "food_drink",
        "target_ids": [target["id"]],
        "title": "조건X와 음료Y 주의",
        "summary": "조건X에 해당하면 가상성분A를 음료Y와 함께 먹지 않도록 주의해요.",
        "action": "조건X에 해당하면 음료Y와 함께 먹지 않도록 주의하세요.",
        "evidence": [{"chunk_id": "synthetic-a", "exact_quote": quote}],
        "grounded": False,
    }
    bad = {
        **good,
        "title": "근거 없는 안전 주장",
        "summary": "가상성분A는 누구에게나 안전해요.",
        "action": "조건에 관계없이 음료Y와 함께 먹어도 돼요.",
    }
    wrong_target = {**good, "title": "다른 제품 주장", "target_ids": [other["id"]]}
    start = time.monotonic()
    plan, draft, verified = await asyncio.gather(
        _invoke(
            pipeline._planner,
            {"targets": [target, other], "allowed_sections": ["food_drink", "lifestyle", "additional_precautions"]},
        ),
        _invoke(pipeline._claim_writer, trusted),
        _invoke(
            pipeline._verifier, {"candidate_claims": {"claims": [good, bad, wrong_target]}, "trusted_evidence": trusted}
        ),
    )
    plan = plan.model_dump(mode="json")
    kept = verified["claims"]
    checks = {
        "planner_all_sections": {item["section_id"] for item in plan["sections"]}
        == {"food_drink", "lifestyle", "additional_precautions"},
        "planner_all_targets": all(set(item["target_ids"]) == {target["id"], other["id"]} for item in plan["sections"]),
        "writer_supported_conditional_claim": bool(draft["claims"])
        and all(
            "조건X" in item["summary"] and "조건X" in item["action"] and item["target_ids"] == [target["id"]]
            for item in draft["claims"]
        ),
        "writer_exact_quotes": bool(draft["claims"])
        and all(
            len(item["evidence"]) == 1
            and item["evidence"][0]["chunk_id"] == "synthetic-a"
            and bool(item["evidence"][0]["exact_quote"])
            and item["evidence"][0]["exact_quote"] in quote
            for item in draft["claims"]
        ),
        "verifier_only_good_claim": len(kept) == 1
        and kept[0]["title"] == good["title"]
        and kept[0]["target_ids"] == good["target_ids"]
        and kept[0]["grounded"],
        "verifier_preserves_valid_text": len(kept) == 1
        and {k: v for k, v in kept[0].items() if k != "grounded"} == {k: v for k, v in good.items() if k != "grounded"},
    }
    print(
        json.dumps(
            {
                "synthetic_only": True,
                "model": settings.OPENAI_CHAT_MODEL,
                "elapsed_seconds": round(time.monotonic() - start, 2),
                "checks": checks,
                "plan": plan,
                "draft": draft,
                "verified": verified,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live", action="store_true", help="Allow three billed synthetic model calls")
    if not parser.parse_args().run_live:
        parser.error("Pass --run-live to opt into synthetic model calls")
    asyncio.run(run())
