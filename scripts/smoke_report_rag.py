"""Opt-in, synthetic-only live smoke test; never reads patient data or enables RAG.

Run from the repository root with --run-live. Uses the configured OpenAI/Qdrant
services and therefore incurs a small model/embedding charge. No report is sent.
"""

import argparse
import asyncio
import json
import time

from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.rag.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider
from ai_worker.rag.retrievers.medication_knowledge_retriever import MedicationKnowledgeRetriever
from ai_worker.rag.vectorstores.qdrant_hybrid_knowledge_store import QdrantHybridKnowledgeStore
from ai_worker.rag.vectorstores.qdrant_knowledge_store import QdrantKnowledgeStore
from ai_worker.reports.report_rag_pipeline import ReportRagTarget, build_openai_report_rag_pipeline
from ai_worker.schemas.knowledge import KnowledgeSearchMode


async def run(scenario: str = "vitamin-c", diagnostics: bool = False) -> None:
    settings = Config()
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for the explicit live smoke test")
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=10)
    try:
        kwargs = dict(
            client=client,
            collection_name=settings.KNOWLEDGE_QDRANT_COLLECTION,
            vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
            distance=settings.KNOWLEDGE_VECTOR_DISTANCE,
        )
        store = (
            QdrantKnowledgeStore(**kwargs)
            if settings.KNOWLEDGE_SEARCH_MODE == KnowledgeSearchMode.DENSE
            else QdrantHybridKnowledgeStore(search_mode=settings.KNOWLEDGE_SEARCH_MODE, **kwargs)
        )
        retriever = MedicationKnowledgeRetriever(
            embedding_provider=OpenAIEmbeddingProvider(
                model=settings.OPENAI_EMBEDDING_MODEL,
                dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
                api_key=settings.OPENAI_API_KEY,
                timeout_seconds=10,
                max_retries=0,
            ),
            vector_store=store,
            dataset_version=settings.KNOWLEDGE_DATASET_VERSION,
            min_similarity_score=settings.RAG_MIN_SIMILARITY_SCORE,
        )
        observations = []
        search = retriever.search_with_diagnostics

        async def observed_search(*, execution_plan):
            result = await search(execution_plan=execution_plan)
            observations.append(
                {
                    "query": execution_plan.query_plan.original_query,
                    "entities": execution_plan.query_plan.entity_names,
                    "accepted": len(result.chunks),
                    "chunk_metadata": [
                        {
                            "document_id": chunk.metadata.document_id,
                            "type": chunk.metadata.document_type.value,
                            "ingredients": chunk.metadata.ingredient_names,
                            "drugs": chunk.metadata.drug_names,
                        }
                        for chunk in result.chunks
                    ],
                    "diagnostics": result.diagnostics.model_dump(mode="json", exclude={"candidate_diagnostics"}),
                }
            )
            return result

        if diagnostics:
            retriever.search_with_diagnostics = observed_search
        pipeline = build_openai_report_rag_pipeline(
            retriever=retriever,
            dataset_version=settings.KNOWLEDGE_DATASET_VERSION,
            model=settings.OPENAI_CHAT_MODEL,
            api_key=settings.OPENAI_API_KEY,
        )
        start = time.monotonic()
        targets = [ReportRagTarget(id="supplement:1", item_id=1, item_type="SUPPLEMENT", name="비타민 C")]
        if scenario == "generic-medication":
            targets = [
                ReportRagTarget(
                    "medication:1", 1, "MEDICATION", "아세트아미노펜정500mg", ("아세트아미노펜",), ingredient_only=True
                )
            ]
        elif scenario == "generic-pair":
            targets = [
                ReportRagTarget("medication:1", 1, "MEDICATION", "파모티딘정20mg", ("파모티딘",), ingredient_only=True),
                ReportRagTarget(
                    "medication:2", 2, "MEDICATION", "아세트아미노펜정500mg", ("아세트아미노펜",), ingredient_only=True
                ),
            ]
        elif scenario == "mixed":
            targets.append(ReportRagTarget(id="medication:1", item_id=1, item_type="MEDICATION", name="아세트아미노펜"))
        elif scenario == "large-stack":
            targets = [
                ReportRagTarget(f"medication:{index}", index, "MEDICATION", f"가상등록약{index:02d}")
                for index in range(1, 13)
            ] + [
                ReportRagTarget("supplement:1", 1, "SUPPLEMENT", "가상복합제품A", ("비타민 C",)),
                ReportRagTarget("supplement:2", 2, "SUPPLEMENT", "가상복합제품B", ("비타민 D",)),
            ]
        elif scenario == "commercial-stack":
            names = [
                "펙소나딘정120밀리그램",
                "시네츄라시럽(15mL)",
                "라베뉴정10/500밀리그램",
                "소로펜정",
                "써스펜8시간이알서방정650...",
                "뮤코졸정",
                "코싹엘정",
                "퍼킨정",
                "아세트아미노펜정500mg",
                "세티리진정10mg",
                "암브록솔정30mg",
                "파모티딘정20mg",
            ]
            targets = [ReportRagTarget(f"medication:{i}", i, "MEDICATION", name) for i, name in enumerate(names, 1)] + [
                ReportRagTarget("supplement:1", 1, "SUPPLEMENT", "뉴 엠에스엠 파워 루마-F", ("나트륨",)),
                ReportRagTarget(
                    "supplement:2",
                    2,
                    "SUPPLEMENT",
                    "티로드 이뮨 T-LODE IMMUNE",
                    ("비타민 A", "티아민", "리보플라빈", "나이아신", "비타민 C", "비타민 D", "탄수화물"),
                ),
            ]
        result = await pipeline.run(
            targets=targets,
            remaining_seconds=100,
        )
        print(
            json.dumps(
                {
                    "synthetic_only": True,
                    "scenario": scenario,
                    "model": settings.OPENAI_CHAT_MODEL,
                    "dataset": settings.KNOWLEDGE_DATASET_VERSION,
                    "elapsed_seconds": round(time.monotonic() - start, 2),
                    "verified_card_count": len(result.cards),
                    "source_count": len(result.sources),
                    "metrics": result.metrics,
                    **({"retrieval_observations": observations} if diagnostics else {}),
                    "cards": [card.model_dump() for card in result.cards],
                    "sections": [section.model_dump() for section in result.section_statuses],
                    "source_documents": [
                        {
                            "title": source.title,
                            "chunk_id": source.chunk_id,
                            "dataset_version": source.dataset_version,
                            "quote": source.quote,
                        }
                        for source in result.sources
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if not result.cards:
            raise SystemExit("INCOMPLETE: no grounded guidance was produced; keep feature disabled")
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live", action="store_true", help="Explicitly allow the billed synthetic API check")
    parser.add_argument(
        "--scenario",
        choices=("vitamin-c", "mixed", "large-stack", "commercial-stack", "generic-medication", "generic-pair"),
        default="vitamin-c",
    )
    parser.add_argument("--diagnostics", action="store_true", help="Print synthetic retrieval scores and counts")
    args = parser.parse_args()
    if not args.run_live:
        parser.error("Pass --run-live to opt into model/embedding calls; no patient or DB data is used")
    asyncio.run(run(args.scenario, diagnostics=args.diagnostics))
