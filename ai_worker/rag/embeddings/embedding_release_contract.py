from dataclasses import dataclass

from ai_worker.schemas.knowledge import KnowledgeVectorDistance


@dataclass(frozen=True)
class EmbeddingReleaseContract:
    """벡터 재사용과 활성화 전에 확인하는 임베딩 릴리스 식별자."""

    model_name: str
    dimensions: int
    distance: KnowledgeVectorDistance
    tokenizer_encoding: str
    chunking_version: str
    embedding_text_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "model_name",
            "tokenizer_encoding",
            "chunking_version",
            "embedding_text_version",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")
        if self.dimensions <= 0:
            raise ValueError("임베딩 차원은 0보다 커야 합니다.")

    def assert_reuse_compatible(self, source: "EmbeddingReleaseContract") -> None:
        if self.identity != source.identity:
            raise ValueError("벡터 재사용은 동일한 임베딩 릴리스 계약에서만 허용됩니다.")

    @property
    def identity(self) -> tuple[str, int, str, str, str, str]:
        return (
            self.model_name,
            self.dimensions,
            self.distance.value,
            self.tokenizer_encoding,
            self.chunking_version,
            self.embedding_text_version,
        )

    def to_manifest(
        self,
        *,
        collection_name: str,
        dataset_version: str,
    ) -> dict[str, str | int]:
        return {
            "collection_name": collection_name,
            "dataset_version": dataset_version,
            "embedding_model": self.model_name,
            "embedding_dimensions": self.dimensions,
            "distance": self.distance.value,
            "tokenizer_encoding": self.tokenizer_encoding,
            "chunking_version": self.chunking_version,
            "embedding_text_version": self.embedding_text_version,
        }
