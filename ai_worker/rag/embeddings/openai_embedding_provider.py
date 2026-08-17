from typing import Protocol

from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr


class AsyncEmbeddingClient(Protocol):
    async def aembed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]: ...

    async def aembed_query(
        self,
        query: str,
    ) -> list[float]: ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        model: str,
        dimensions: int,
        api_key: SecretStr | None = None,
        client: AsyncEmbeddingClient | None = None,
    ) -> None:
        normalized_model = model.strip()

        if not normalized_model:
            raise ValueError(
                "임베딩 모델명은 "
                "비어 있을 수 없습니다."
            )

        if dimensions <= 0:
            raise ValueError(
                "임베딩 차원은 "
                "0보다 커야 합니다."
            )

        self._model_name = normalized_model
        self._dimension = dimensions

        self._client: AsyncEmbeddingClient = (
            client
            if client is not None
            else OpenAIEmbeddings(
                model=normalized_model,
                dimensions=dimensions,
                api_key=api_key,
            )
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        normalized_texts = [
            text.strip()
            for text in texts
        ]

        if any(
            not text
            for text in normalized_texts
        ):
            raise ValueError(
                "임베딩할 문서는 "
                "비어 있을 수 없습니다."
            )

        vectors = (
            await self._client.aembed_documents(
                normalized_texts
            )
        )

        if len(vectors) != len(normalized_texts):
            raise ValueError(
                "문서 개수와 임베딩 벡터 "
                "개수가 일치하지 않습니다."
            )

        for vector in vectors:
            self._validate_vector(vector)

        return vectors

    async def embed_query(
        self,
        query: str,
    ) -> list[float]:
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError(
                "검색어는 비어 있을 수 없습니다."
            )

        vector = await self._client.aembed_query(
            normalized_query
        )

        self._validate_vector(vector)

        return vector

    def _validate_vector(
        self,
        vector: list[float],
    ) -> None:
        if len(vector) != self._dimension:
            raise ValueError(
                "임베딩 벡터 차원이 설정값과 "
                "일치하지 않습니다."
            )
