from pathlib import Path

from pypdf import PdfReader

from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeMetadata,
    KnowledgePage,
)


class KnowledgePdfLoader:
    def load(
        self,
        file_path: Path,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            raise ValueError("PDF 파일만 불러올 수 있습니다.")

        reader = PdfReader(path)
        pages = [
            KnowledgePage(
                content=content,
                metadata=metadata,
                page_number=page_number,
            )
            for page_number, page in enumerate(reader.pages, start=1)
            if (content := self._extract_text(page, metadata).strip())
        ]
        if not pages:
            raise ValueError("PDF에서 추출 가능한 텍스트를 찾지 못했습니다.")
        return pages

    @staticmethod
    def _extract_text(page, metadata: KnowledgeMetadata) -> str:
        if metadata.document_type == KnowledgeDocumentType.PHARM_REVIEW:
            return page.extract_text(extraction_mode="layout") or ""
        return page.extract_text() or ""
