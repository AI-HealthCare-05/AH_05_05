import argparse
import json
from pathlib import Path

from ai_worker.rag.loaders.knowledge_pdf_loader import KnowledgePdfLoader
from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.normalizers.knowledge_normalizer import KnowledgeNormalizer
from ai_worker.rag.splitters.knowledge_splitter import KnowledgeSplitter
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgePilotPreprocessingService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="대표 약·영양제 PDF를 섹션/토큰 기준 JSONL 청크로 전처리합니다.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/knowledge/manifests/pilot_manifest.json"),
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("data/knowledge/manifests/sources.yaml"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/knowledge/processed"),
    )
    parser.add_argument("--dataset-version", default="knowledge-pilot-v1")
    parser.add_argument(
        "--tokenizer-encoding",
        choices=("cl100k_base", "o200k_base"),
        default="cl100k_base",
    )
    parser.add_argument(
        "--interaction-annotations",
        type=Path,
        default=Path("data/knowledge/manifests/interaction_annotations.yaml"),
        help="문서별로 검수한 직접 상호작용 쌍 주석 매니페스트입니다.",
    )
    return parser.parse_args()


def build_splitter(
    *,
    tokenizer_encoding: str,
    interaction_annotations: KnowledgeInteractionAnnotationRegistry | None = None,
) -> KnowledgeSplitter:
    return KnowledgeSplitter(
        interaction_annotations=interaction_annotations,
        tokenizer_encoding=tokenizer_encoding,
    )


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    interaction_annotations = KnowledgeInteractionAnnotationRegistry.from_yaml(
        repo_root / args.interaction_annotations,
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=repo_root,
        loader=KnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=build_splitter(
            tokenizer_encoding=args.tokenizer_encoding,
            interaction_annotations=interaction_annotations,
        ),
    )
    result = service.preprocess(
        manifest_path=repo_root / args.manifest,
        sources_path=repo_root / args.sources,
        output_root=repo_root / args.output,
        dataset_version=args.dataset_version,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
