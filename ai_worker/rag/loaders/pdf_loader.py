import re
from pathlib import Path

from pypdf import PdfReader

from ai_worker.schemas.guideline import (
    GuidelineDocument,
    GuidelineMetadata,
)


class PdfLoader:
    def load(
        self,
        file_path: Path,
        metadata: GuidelineMetadata,
    ) -> list[GuidelineDocument]:
        path = Path(file_path)

        if path.suffix.lower() != ".pdf":
            raise ValueError("PDF 파일만 불러올 수 있습니다.")

        if not path.exists():
            raise FileNotFoundError(path)

        reader = PdfReader(path)
        documents: list[GuidelineDocument] = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            content = self._clean_text(page.extract_text() or "")

            if not content:
                continue

            page_metadata = metadata.model_copy(
                update={
                    "page_number": page_number,
                },
                deep=True,
            )

            documents.append(
                GuidelineDocument(
                    content=content,
                    metadata=page_metadata,
                )
            )

        if not documents:
            raise ValueError("PDF에서 추출 가능한 텍스트를 찾지 못했습니다.")

        return documents

    @staticmethod
    def _clean_text(value: str) -> str:
        normalized = value.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        normalized = re.sub(
            r"[ \t]+",
            " ",
            normalized,
        )
        normalized = re.sub(
            r" *\n *",
            "\n",
            normalized,
        )
        normalized = re.sub(
            r"\n{3,}",
            "\n\n",
            normalized,
        )

        return normalized.strip()
