import argparse
from pathlib import Path

from ai_worker.rag.evaluators.knowledge_release_comparator import (
    KnowledgeReleaseComparator,
)
from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationReport,
    KnowledgeReleaseComparisonReport,
    KnowledgeReleaseDecision,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="두 Knowledge 검색 평가 보고서를 정확도 우선으로 비교합니다.")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def load_report(path: Path) -> KnowledgeEvaluationReport:
    return KnowledgeEvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))


def compare_files(
    *,
    baseline_path: Path,
    candidate_path: Path,
    output_path: Path,
) -> KnowledgeReleaseComparisonReport:
    comparison = KnowledgeReleaseComparator().compare(
        baseline=load_report(baseline_path),
        candidate=load_report(candidate_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        comparison.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return comparison


def main() -> None:
    args = parse_args()
    comparison = compare_files(
        baseline_path=args.baseline,
        candidate_path=args.candidate,
        output_path=args.output,
    )
    print(comparison.model_dump_json(indent=2))
    raise SystemExit(0 if comparison.decision == KnowledgeReleaseDecision.ACTIVATE else 2)


if __name__ == "__main__":
    main()
