from ai_worker.rag.resolvers.guideline_conflict_resolver import (
    RuleBasedGuidelineConflictResolver,
)
from ai_worker.schemas.enums import (
    ConflictStatus,
    InstructionType,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.patient import (
    PatientContext,
    PatientInstruction,
)


def build_patient_context(
    *,
    with_instruction: bool = True,
) -> PatientContext:
    instructions = []

    if with_instruction:
        instructions.append(
            PatientInstruction(
                instruction_type=(
                    InstructionType.WARNING_SIGN
                ),
                content=(
                    "심한 통증이 발생하면 "
                    "의료기관에 연락하세요."
                ),
                source_field_id=1001,
            )
        )

    return PatientContext(
        user_id=1,
        care_episode_id=100,
        diagnoses=["뇌졸중"],
        instructions=instructions,
    )


def build_chunk(
    *,
    chunk_id: str,
    topic: str | None,
) -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id=chunk_id,
        content=f"{chunk_id} 공공 가이드라인",
        similarity_score=0.9,
        metadata=GuidelineMetadata(
            document_id="stroke-guideline",
            title="Stroke Guideline",
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic=topic,
            page_number=1,
        ),
    )


async def test_resolve_returns_not_applicable_without_chunks() -> None:
    resolver = (
        RuleBasedGuidelineConflictResolver()
    )

    result = await resolver.resolve(
        patient_context=build_patient_context(),
        guideline_chunks=[],
    )

    assert (
        result.status
        == ConflictStatus.NOT_APPLICABLE
    )
    assert result.usable_guideline_chunks == []
    assert result.excluded_guideline_chunks == []


async def test_resolve_uses_all_chunks_without_patient_instruction() -> None:
    resolver = (
        RuleBasedGuidelineConflictResolver()
    )
    chunks = [
        build_chunk(
            chunk_id="warning-chunk",
            topic="WARNING_SIGN",
        )
    ]

    result = await resolver.resolve(
        patient_context=build_patient_context(
            with_instruction=False
        ),
        guideline_chunks=chunks,
    )

    assert (
        result.status
        == ConflictStatus.NO_CONFLICT
    )
    assert result.usable_guideline_chunks == chunks
    assert result.excluded_guideline_chunks == []


async def test_resolve_excludes_same_topic_chunk() -> None:
    resolver = (
        RuleBasedGuidelineConflictResolver()
    )
    conflicting_chunk = build_chunk(
        chunk_id="warning-chunk",
        topic="WARNING_SIGN",
    )

    result = await resolver.resolve(
        patient_context=build_patient_context(),
        guideline_chunks=[conflicting_chunk],
    )

    assert (
        result.status
        == ConflictStatus.PUBLIC_SOURCE_EXCLUDED
    )
    assert result.usable_guideline_chunks == []
    assert result.excluded_guideline_chunks == [
        conflicting_chunk
    ]


async def test_resolve_keeps_non_conflicting_topic() -> None:
    resolver = (
        RuleBasedGuidelineConflictResolver()
    )
    conflicting_chunk = build_chunk(
        chunk_id="warning-chunk",
        topic="WARNING_SIGN",
    )
    usable_chunk = build_chunk(
        chunk_id="lifestyle-chunk",
        topic="LIFESTYLE",
    )

    result = await resolver.resolve(
        patient_context=build_patient_context(),
        guideline_chunks=[
            conflicting_chunk,
            usable_chunk,
        ],
    )

    assert (
        result.status
        == ConflictStatus.PATIENT_DATA_PRIORITY
    )
    assert result.usable_guideline_chunks == [
        usable_chunk
    ]
    assert result.excluded_guideline_chunks == [
        conflicting_chunk
    ]


async def test_resolve_requires_review_when_topic_is_missing() -> None:
    resolver = (
        RuleBasedGuidelineConflictResolver()
    )
    unknown_chunk = build_chunk(
        chunk_id="unknown-chunk",
        topic=None,
    )

    result = await resolver.resolve(
        patient_context=build_patient_context(),
        guideline_chunks=[unknown_chunk],
    )

    assert (
        result.status
        == ConflictStatus.REVIEW_REQUIRED
    )
    assert result.usable_guideline_chunks == []
    assert result.excluded_guideline_chunks == [
        unknown_chunk
    ]
    assert result.reason is not None
