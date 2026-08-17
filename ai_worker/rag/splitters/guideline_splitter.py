from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)

from ai_worker.schemas.guideline import (
    GuidelineDocument,
)


class GuidelineSplitter:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError(
                "chunk_size는 0보다 커야 합니다."
            )

        if chunk_overlap < 0:
            raise ValueError(
                "chunk_overlap은 0 이상이어야 합니다."
            )

        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap은 chunk_size보다 "
                "작아야 합니다."
            )

        self._splitter = (
            RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=len,
                is_separator_regex=False,
            )
        )

    def split(
        self,
        documents: list[GuidelineDocument],
    ) -> list[GuidelineDocument]:
        chunks: list[GuidelineDocument] = []

        for document in documents:
            split_contents = (
                self._splitter.split_text(
                    document.content
                )
            )

            for content in split_contents:
                cleaned_content = content.strip()

                if not cleaned_content:
                    continue

                chunks.append(
                    GuidelineDocument(
                        content=cleaned_content,
                        metadata=(
                            document.metadata.model_copy(
                                deep=True,
                            )
                        ),
                    )
                )

        return chunks
