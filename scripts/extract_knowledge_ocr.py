import argparse
import asyncio
import json
from io import BytesIO
from pathlib import Path

import pdfplumber

from ai_worker.schemas.knowledge_ocr import KnowledgeOcrBlock, KnowledgeOcrBoundingBox
from ai_worker.schemas.knowledge_recovery import KnowledgeOcrManifestEntry
from ai_worker.services.knowledge_ocr_extraction_service import (
    KnowledgeOcrExtractionService,
    KnowledgeOcrRenderedPage,
)
from ai_worker.services.knowledge_tesseract_ocr_service import (
    TesseractKnowledgeOcrProvider,
    TesseractThenFallbackKnowledgeOcrProvider,
)


class PdfPlumberKnowledgeRasterizer:
    name = "pdfplumber-pdfium"
    version = "pdfplumber"

    def page_count(self, source_path: Path) -> int:
        with pdfplumber.open(source_path) as document:
            return len(document.pages)

    def render_page(
        self,
        source_path: Path,
        page_number: int,
        dpi: int,
    ) -> KnowledgeOcrRenderedPage:
        with pdfplumber.open(source_path) as document:
            page = document.pages[page_number - 1]
            image = page.to_image(resolution=dpi).original.convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=95, optimize=False)
            return KnowledgeOcrRenderedPage(
                image_bytes=buffer.getvalue(),
                width=float(image.width),
                height=float(image.height),
                rotation_degrees=0,
            )


class ClovaGeneralKnowledgeOcrAdapter:
    name = "clova-general-ocr-v2"
    version = "V2"

    def __init__(self, provider) -> None:
        self._provider = provider

    async def recognize(self, image_bytes: bytes) -> list[KnowledgeOcrBlock]:
        result = await self._provider.recognize(image_bytes)
        blocks: list[KnowledgeOcrBlock] = []
        for source_block in result.blocks:
            if source_block.confidence is None or source_block.bbox is None:
                raise ValueError("OCR block에 신뢰도 또는 좌표가 없습니다.")
            points = source_block.bbox
            blocks.append(
                KnowledgeOcrBlock(
                    block_id=source_block.block_id,
                    text=source_block.text,
                    confidence=source_block.confidence,
                    bbox=KnowledgeOcrBoundingBox(
                        x0=min(point.x for point in points),
                        top=min(point.y for point in points),
                        x1=max(point.x for point in points),
                        bottom=max(point.y for point in points),
                    ),
                    line_break=source_block.line_break,
                )
            )
        return blocks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="지식 코퍼스 OCR 대기 문서를 공급자 중립 artifact로 추출합니다.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--ocr-manifest",
        type=Path,
        default=Path("data/knowledge/manifests/knowledge_ocr_manifest.jsonl"),
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("data/knowledge/processed/ocr-artifacts"),
    )
    parser.add_argument(
        "--document-id",
        action="append",
        default=[],
        help="대표 문서만 OCR할 때 지정합니다. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument(
        "--engine",
        choices=("tesseract", "clova", "tesseract-with-clova-fallback"),
        default="tesseract",
        help="기본값은 외부 전송 없는 로컬 Tesseract입니다.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--allow-clova-fallback",
        action="store_true",
        help="저신뢰 Tesseract 페이지를 CLOVA OCR에 전송하도록 명시적으로 허용합니다.",
    )
    parser.add_argument("--allow-demo-restricted-ocr", action="store_true")
    return parser.parse_args()


def _load_manifest(path: Path) -> list[KnowledgeOcrManifestEntry]:
    entries = [
        KnowledgeOcrManifestEntry.model_validate_json(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not entries:
        raise ValueError("OCR 매니페스트가 비어 있습니다.")
    return entries


def _select_entries(
    entries: list[KnowledgeOcrManifestEntry],
    document_ids: list[str],
) -> list[KnowledgeOcrManifestEntry]:
    if not document_ids:
        return entries

    requested_ids = set(document_ids)
    entries_by_id = {entry.document_id: entry for entry in entries}
    missing_ids = requested_ids.difference(entries_by_id)
    if missing_ids:
        missing = ", ".join(sorted(missing_ids))
        raise ValueError(f"OCR 매니페스트에 없는 document_id입니다: {missing}")
    return [entry for entry in entries if entry.document_id in requested_ids]


async def _execute(
    *,
    entries: list[KnowledgeOcrManifestEntry],
    repo_root: Path,
    artifact_root: Path,
    engine: str,
) -> dict[str, object]:
    if engine == "tesseract":
        return await _extract_artifacts(
            entries=entries,
            repo_root=repo_root,
            artifact_root=artifact_root,
            provider=TesseractKnowledgeOcrProvider(),
            engine=engine,
        )

    from app.core.config import Config
    from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider

    settings = Config()
    endpoint = settings.CLOVA_GENERAL_OCR_INVOKE_URL
    secret = settings.CLOVA_GENERAL_OCR_SECRET
    if endpoint is None or secret is None:
        raise ValueError("CLOVA General OCR 설정이 필요합니다.")
    async with ClovaGeneralOcrProvider(
        endpoint=endpoint,
        secret=secret.get_secret_value(),
    ) as provider:
        clova_provider = ClovaGeneralKnowledgeOcrAdapter(provider)
        selected_provider = (
            clova_provider
            if engine == "clova"
            else TesseractThenFallbackKnowledgeOcrProvider(
                primary=TesseractKnowledgeOcrProvider(),
                fallback=clova_provider,
            )
        )
        return await _extract_artifacts(
            entries=entries,
            repo_root=repo_root,
            artifact_root=artifact_root,
            provider=selected_provider,
            engine=engine,
        )


async def _extract_artifacts(
    *,
    entries: list[KnowledgeOcrManifestEntry],
    repo_root: Path,
    artifact_root: Path,
    provider,
    engine: str,
) -> dict[str, object]:
    completed_document_ids: list[str] = []
    service = KnowledgeOcrExtractionService(
        rasterizer=PdfPlumberKnowledgeRasterizer(),
        provider=provider,
    )
    for entry in entries:
        await service.extract(
            entry=entry,
            source_path=repo_root / entry.repo_path,
            artifact_root=artifact_root,
        )
        completed_document_ids.append(entry.document_id)
    return {
        "mode": "EXECUTED",
        "ocr_engine": engine,
        "ocr_document_count": len(entries),
        "completed_document_ids": completed_document_ids,
        "artifact_root": str(artifact_root),
    }


def _external_ocr_mode(engine: str) -> str:
    if engine == "tesseract":
        return "NONE"
    if engine == "clova":
        return "ALL_PAGES"
    return "FALLBACK_ONLY"


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    entries = _select_entries(
        _load_manifest(repo_root / args.ocr_manifest),
        args.document_id,
    )
    artifact_root = repo_root / args.artifact_root
    demo_restricted_count = sum(entry.access_scope == "DEMO_RESTRICTED" for entry in entries)
    if not args.execute:
        print(
            json.dumps(
                {
                    "mode": "DRY_RUN",
                    "ocr_engine": args.engine,
                    "external_ocr_mode": _external_ocr_mode(args.engine),
                    "ocr_document_count": len(entries),
                    "demo_restricted_document_count": demo_restricted_count,
                    "artifact_root": str(artifact_root),
                },
                ensure_ascii=False,
            ),
        )
        return
    if args.engine == "tesseract-with-clova-fallback" and not args.allow_clova_fallback:
        raise ValueError("CLOVA fallback 실행에는 --allow-clova-fallback가 필요합니다.")
    if args.engine != "tesseract" and demo_restricted_count and not args.allow_demo_restricted_ocr:
        raise ValueError("DEMO_RESTRICTED OCR 전송에는 --allow-demo-restricted-ocr가 필요합니다.")
    print(
        json.dumps(
            asyncio.run(
                _execute(
                    entries=entries,
                    repo_root=repo_root,
                    artifact_root=artifact_root,
                    engine=args.engine,
                )
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
