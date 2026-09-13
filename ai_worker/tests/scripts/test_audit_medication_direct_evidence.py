from ai_worker.evaluation.medication_direct_evidence_audit import (
    DirectEvidenceAttribution,
    DirectEvidenceAuditReport,
    DirectEvidenceTargetObservation,
)
from scripts import audit_medication_direct_evidence as module


def test_cli_accepts_a_qdrant_gold_query_filter() -> None:
    args = module.parse_args(
        [
            "--evaluation-file",
            "data/knowledge/evaluation/user_expression_queries_v3.yaml",
            "--output",
            "output/direct-evidence.md",
            "--query-id",
            "drug-food-tylenol-alcohol",
        ]
    )

    assert args.query_ids == ["drug-food-tylenol-alcohol"]


def test_markdown_report_includes_stage_summary_and_target_rows() -> None:
    report = DirectEvidenceAuditReport.from_attributions(
        collection_name="medication_knowledge_full_v15",
        dataset_version="knowledge-full-v15",
        attributions=[
            DirectEvidenceAttribution.from_observation(
                DirectEvidenceTargetObservation(
                    query_id="drug-food-tylenol-alcohol",
                    collection_name="medication_knowledge_full_v15",
                    dataset_version="knowledge-full-v15",
                    expected_document_id="gold-document",
                    target_payload_present=True,
                    payload_dataset_versions=["knowledge-full-v15"],
                    payload_pair_key_matched=True,
                    exact_pair_raw_rank=1,
                    refined_rank=None,
                )
            )
        ],
    )

    markdown = module.render_markdown(report)

    assert "REFINER_DROPPED" in markdown
    assert "drug-food-tylenol-alcohol" in markdown
    assert "gold-document" in markdown
    assert "Top-5" in markdown
