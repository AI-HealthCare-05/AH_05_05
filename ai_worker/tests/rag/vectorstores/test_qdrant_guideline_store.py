from qdrant_client import AsyncQdrantClient

from ai_worker.rag.vectorstores.qdrant_guideline_store import (
    QdrantGuidelineStore,
)
from ai_worker.schemas.guideline import (
    GuidelineDocument,
    GuidelineMetadata,
    GuidelineSearchQuery,
)


def build_document(
    *,
    document_id: str,
    condition: str,
    content: str,
    care_phase: str = "POST_DISCHARGE",
    topic: str | None = None,
) -> GuidelineDocument:
    return GuidelineDocument(
        content=content,
        metadata=GuidelineMetadata(
            document_id=document_id,
            title=f"{condition} Guideline",
            organization="Test Organization",
            condition=condition,
            care_phase=care_phase,
            topic=topic,
            page_number=1,
        ),
    )


async def test_ensure_collection_creates_collection() -> None:
    client = AsyncQdrantClient(location=":memory:")

    try:
        store = QdrantGuidelineStore(
            client=client,
            collection_name="test_guidelines",
            vector_size=3,
        )

        await store.ensure_collection()

        assert await client.collection_exists("test_guidelines")
    finally:
        await client.close()


async def test_upsert_chunks_stores_documents() -> None:
    client = AsyncQdrantClient(location=":memory:")

    try:
        store = QdrantGuidelineStore(
            client=client,
            collection_name="test_guidelines",
            vector_size=3,
        )
        await store.ensure_collection()

        document = build_document(
            document_id="stroke-2020",
            condition="STROKE",
            content="퇴원 후 처방된 약을 지시에 따라 복용합니다.",
            topic="MEDICATION",
        )

        point_ids = await store.upsert_chunks(
            chunks=[document],
            vectors=[[1.0, 0.0, 0.0]],
        )

        count_result = await client.count(
            collection_name="test_guidelines",
            exact=True,
        )

        assert len(point_ids) == 1
        assert count_result.count == 1
    finally:
        await client.close()


async def test_upsert_same_chunk_does_not_create_duplicate() -> None:
    client = AsyncQdrantClient(location=":memory:")

    try:
        store = QdrantGuidelineStore(
            client=client,
            collection_name="test_guidelines",
            vector_size=3,
        )
        await store.ensure_collection()

        document = build_document(
            document_id="stroke-2020",
            condition="STROKE",
            content="퇴원 후 처방된 약을 지시에 따라 복용합니다.",
        )

        first_ids = await store.upsert_chunks(
            chunks=[document],
            vectors=[[1.0, 0.0, 0.0]],
        )
        second_ids = await store.upsert_chunks(
            chunks=[document],
            vectors=[[1.0, 0.0, 0.0]],
        )

        count_result = await client.count(
            collection_name="test_guidelines",
            exact=True,
        )

        assert first_ids == second_ids
        assert count_result.count == 1
    finally:
        await client.close()


async def test_search_filters_by_condition_and_topic() -> None:
    client = AsyncQdrantClient(location=":memory:")

    try:
        store = QdrantGuidelineStore(
            client=client,
            collection_name="test_guidelines",
            vector_size=3,
        )
        await store.ensure_collection()

        documents = [
            build_document(
                document_id="stroke-medication",
                condition="STROKE",
                content="뇌졸중 환자의 퇴원 후 복약 안내",
                topic="MEDICATION",
            ),
            build_document(
                document_id="stroke-lifestyle",
                condition="STROKE",
                content="뇌졸중 환자의 퇴원 후 생활관리 안내",
                topic="LIFESTYLE",
            ),
            build_document(
                document_id="heart-failure-medication",
                condition="HEART_FAILURE",
                content="심부전 환자의 퇴원 후 복약 안내",
                topic="MEDICATION",
            ),
        ]

        await store.upsert_chunks(
            chunks=documents,
            vectors=[
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.99, 0.01, 0.0],
            ],
        )

        results = await store.search(
            query_vector=[1.0, 0.0, 0.0],
            search_query=GuidelineSearchQuery(
                query="퇴원 후 복약",
                condition="STROKE",
                care_phase="POST_DISCHARGE",
                topic="MEDICATION",
                limit=5,
            ),
        )

        assert len(results) == 1
        assert results[0].metadata.condition == "STROKE"
        assert results[0].metadata.topic == "MEDICATION"
        assert results[0].content == ("뇌졸중 환자의 퇴원 후 복약 안내")
        assert results[0].similarity_score is not None
    finally:
        await client.close()


async def test_upsert_rejects_vector_count_mismatch() -> None:
    client = AsyncQdrantClient(location=":memory:")

    try:
        store = QdrantGuidelineStore(
            client=client,
            collection_name="test_guidelines",
            vector_size=3,
        )

        document = build_document(
            document_id="stroke-2020",
            condition="STROKE",
            content="퇴원 후 관리 안내",
        )

        try:
            await store.upsert_chunks(
                chunks=[document],
                vectors=[],
            )
        except ValueError as error:
            assert "개수" in str(error)
        else:
            raise AssertionError("ValueError가 발생해야 합니다.")
    finally:
        await client.close()


async def test_delete_by_document_id_removes_only_matching_chunks() -> None:
    client = AsyncQdrantClient(location=":memory:")

    try:
        store = QdrantGuidelineStore(
            client=client,
            collection_name="test_guidelines",
            vector_size=3,
        )
        await store.ensure_collection()

        documents = [
            build_document(
                document_id="stroke-2020",
                condition="STROKE",
                content="뇌졸중 퇴원 후 복약 안내",
            ),
            build_document(
                document_id="stroke-2020",
                condition="STROKE",
                content="뇌졸중 퇴원 후 생활관리 안내",
            ),
            build_document(
                document_id="heart-failure-2020",
                condition="HEART_FAILURE",
                content="심부전 퇴원 후 생활관리 안내",
            ),
        ]

        await store.upsert_chunks(
            chunks=documents,
            vectors=[
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.8, 0.2, 0.0],
            ],
        )

        await store.delete_by_document_id("stroke-2020")

        remaining_points, _ = await client.scroll(
            collection_name="test_guidelines",
            limit=10,
            with_payload=True,
            with_vectors=False,
        )

        assert len(remaining_points) == 1

        remaining_payload = remaining_points[0].payload
        assert remaining_payload is not None
        assert remaining_payload["metadata"]["document_id"] == "heart-failure-2020"
    finally:
        await client.close()


async def test_delete_by_document_id_rejects_blank_id() -> None:
    client = AsyncQdrantClient(location=":memory:")

    try:
        store = QdrantGuidelineStore(
            client=client,
            collection_name="test_guidelines",
            vector_size=3,
        )

        try:
            await store.delete_by_document_id("   ")
        except ValueError as error:
            assert "문서 ID" in str(error)
        else:
            raise AssertionError("ValueError가 발생해야 합니다.")
    finally:
        await client.close()
