"""Bounded, observational Dense/Hybrid Knowledge retrieval comparison.

Document-ID metrics are retrieval proxies, not clinical relevance or adoption criteria.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from time import perf_counter

from qdrant_client.http import models

from ai_worker.core.config import Config
from ai_worker.rag.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider
from ai_worker.rag.evaluators.knowledge_retrieval_evaluator import KnowledgeRetrievalEvaluator
from ai_worker.rag.vectorstores.qdrant_hybrid_knowledge_store import QdrantHybridKnowledgeStore
from ai_worker.rag.vectorstores.qdrant_knowledge_store import QdrantKnowledgeStore
from ai_worker.schemas.knowledge import KnowledgeSearchMode, KnowledgeVectorDistance
from scripts.evaluate_knowledge_retrieval import create_qdrant_client, load_evaluation_manifest, require_api_key


def _eligible_filter(search_query):
    query_filter = QdrantKnowledgeStore._build_filter(search_query)
    query_filter.must.append(
        models.FieldCondition(
            key="metadata.index_eligible",
            match=models.MatchValue(value=True),
        )
    )
    query_filter.must.append(
        models.FieldCondition(
            key="metadata.access_scope",
            match=models.MatchAny(any=["PUBLIC", "DEMO_RESTRICTED"]),
        )
    )
    return query_filter


class EligibleDenseStore(QdrantKnowledgeStore):
    _build_filter = staticmethod(_eligible_filter)


class EligibleHybridStore(QdrantHybridKnowledgeStore):
    _build_filter = staticmethod(_eligible_filter)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-file", type=Path, required=True)
    parser.add_argument("--dense-collection", required=True)
    parser.add_argument("--hybrid-collection", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    if args.output.suffix.lower() != ".json":
        parser.error("--output must be JSON (.json)")
    if not args.dataset_version.strip() or not args.dense_collection.strip() or not args.hybrid_collection.strip():
        parser.error("dataset version and collection names must not be empty")
    if args.dense_collection == args.hybrid_collection:
        parser.error("collections must differ")
    return args


async def verify_collections(client, dense_name, hybrid_name, dataset_version, dimension, distance):  # noqa: C901
    """Stream payloads and dense vectors; compare canonical point fingerprints."""
    fingerprints = {}
    for name, hybrid in ((dense_name, False), (hybrid_name, True)):
        info = await client.get_collection(name)
        vectors = info.config.params.vectors
        sparse = info.config.params.sparse_vectors
        vector = vectors.get("dense") if hybrid and isinstance(vectors, dict) else vectors
        if not hybrid and not isinstance(vectors, models.VectorParams):
            raise ValueError(f"{name}: expected unnamed vector")
        if not isinstance(vector, models.VectorParams):
            raise ValueError(f"{name}: expected {'named dense' if hybrid else 'unnamed'} vector")
        if hybrid and (
            not isinstance(sparse, dict)
            or not isinstance(sparse.get("bm25"), models.SparseVectorParams)
            or sparse["bm25"].modifier != models.Modifier.IDF
        ):
            raise ValueError(f"{name}: expected bm25 sparse vector with IDF")
        if vector.size != dimension:
            raise ValueError(f"{name}: vector dimension mismatch")
        if vector.distance != distance:
            raise ValueError(f"{name}: vector distance mismatch")
        expected_count = (await client.count(collection_name=name, exact=True)).count
        if expected_count <= 0:
            raise ValueError(f"{name}: empty collection")
        offset = None
        seen_ids = set()
        records = []
        while True:
            points, offset = await client.scroll(
                collection_name=name,
                offset=offset,
                limit=256,
                with_payload=True,
                with_vectors=True,
            )
            for point in points:
                payload = point.payload or {}
                metadata = payload.get("metadata")
                if not isinstance(metadata, dict) or metadata.get("dataset_version") != dataset_version:
                    raise ValueError(f"{name}: dataset version mismatch or missing metadata")
                if not all(key in payload for key in ("chunk_id", "content", "embedding_text", "token_count")):
                    raise ValueError(f"{name}: incomplete chunk payload")
                dense_vector = point.vector.get("dense") if hybrid and isinstance(point.vector, dict) else point.vector
                if not isinstance(dense_vector, list) or len(dense_vector) != dimension:
                    raise ValueError(f"{name}: dense vector dimension mismatch or missing vector")
                point_id = str(point.id)
                if point_id in seen_ids:
                    raise ValueError(f"{name}: duplicate point ID")
                seen_ids.add(point_id)
                record = [
                    point_id,
                    payload["chunk_id"],
                    payload["content"],
                    payload["embedding_text"],
                    payload["token_count"],
                    metadata,
                    dense_vector,
                ]
                records.append(
                    hashlib.sha256(
                        json.dumps(record, sort_keys=True, ensure_ascii=False, default=str).encode()
                    ).hexdigest()
                )
            if offset is None:
                break
        if len(records) != expected_count:
            raise ValueError(f"{name}: differing ID count ({len(records)} vs {expected_count})")
        digest = hashlib.sha256("\n".join(sorted(records)).encode()).hexdigest()
        fingerprints[name] = {
            "point_count": len(records),
            "fingerprint": digest,
            "vector_dimension": vector.size,
            "distance": vector.distance.value,
        }
    if fingerprints[dense_name]["point_count"] != fingerprints[hybrid_name]["point_count"]:
        raise ValueError("collection ID count mismatch")
    if fingerprints[dense_name]["fingerprint"] != fingerprints[hybrid_name]["fingerprint"]:
        raise ValueError("collection fingerprint mismatch")
    return fingerprints


def _search_query(case, dataset_version, track):
    query = KnowledgeRetrievalEvaluator._build_search_query(case=case, dataset_version=dataset_version)
    if track == "semantic_unfiltered":
        query = query.model_copy(
            update={
                "document_types": [],
                "drug_names": [],
                "ingredient_names": [],
                "interaction_type": None,
                "interaction_pair_keys": [],
                "special_populations": [],
                "section_types": [],
            }
        )
    return query


async def compare(manifest, embedding_provider, stores, *, repeats=3):  # noqa: C901
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    results = []
    warmup_errors = []
    for query_index, case in enumerate(manifest.cases):
        start = perf_counter()
        vector = await embedding_provider.embed_query(case.query)
        embedding_ms = round((perf_counter() - start) * 1000, 3)
        for track in ("gold_filters", "semantic_unfiltered"):
            query = _search_query(case, manifest.dataset_version, track)
            for mode in ("dense", "hybrid"):
                try:
                    await stores[mode].search(query_vector=vector, search_query=query)
                except Exception as exc:
                    warmup_errors.append(
                        {
                            "query_id": case.query_id,
                            "track": track,
                            "mode": mode,
                            "error": type(exc).__name__,
                        }
                    )
            for repeat in range(repeats):
                order = ("dense", "hybrid") if (query_index + repeat) % 2 == 0 else ("hybrid", "dense")
                for mode in order:
                    entry = {
                        "query_id": case.query_id,
                        "track": track,
                        "repeat": repeat + 1,
                        "mode": mode,
                        "embedding_ms": embedding_ms,
                        "search_refiner_ms": None,
                        "retrieved": [],
                        "document_hit_at_5_proxy": None,
                        "document_reciprocal_rank_proxy": None,
                        "strict_metadata_hit_at_5": None,
                        "strict_metadata_reciprocal_rank": None,
                        "section_coverage": None,
                        "evaluator_hit_at_5": None,
                        "forbidden_entity_or_document_hit_at_5": None,
                        "error": None,
                    }
                    start = perf_counter()
                    try:
                        chunks = await stores[mode].search(query_vector=vector, search_query=query)
                        entry["search_refiner_ms"] = round((perf_counter() - start) * 1000, 3)
                        entry["retrieved"] = [
                            {
                                "chunk_id": chunk.chunk_id,
                                "document_id": chunk.metadata.document_id,
                                "store_score": chunk.similarity_score,
                                "dense_similarity_score": chunk.dense_similarity_score,
                                "content": chunk.content,
                                "metadata": chunk.metadata.model_dump(mode="json"),
                                "strict_metadata_relevant": KnowledgeRetrievalEvaluator._is_relevant(case, chunk),
                                "forbidden_entity_or_document_hit": KnowledgeRetrievalEvaluator._is_disjoint_entity_result(
                                    case, chunk
                                ),
                            }
                            for chunk in chunks
                        ]
                        ranks = [
                            i
                            for i, chunk in enumerate(chunks, 1)
                            if chunk.metadata.document_id in case.expected_document_ids
                        ]
                        entry["document_hit_at_5_proxy"] = any(rank <= 5 for rank in ranks)
                        entry["document_reciprocal_rank_proxy"] = 1 / ranks[0] if ranks else 0.0
                        strict_ranks = [
                            i
                            for i, chunk in enumerate(chunks, 1)
                            if KnowledgeRetrievalEvaluator._is_relevant(case, chunk)
                        ]
                        entry["strict_metadata_hit_at_5"] = any(rank <= 5 for rank in strict_ranks)
                        entry["strict_metadata_reciprocal_rank"] = 1 / strict_ranks[0] if strict_ranks else 0.0
                        entry["section_coverage"] = KnowledgeRetrievalEvaluator._has_expected_section_coverage(
                            case, chunks[:5]
                        )
                        entry["evaluator_hit_at_5"] = entry["strict_metadata_hit_at_5"] and entry["section_coverage"]
                        entry["forbidden_entity_or_document_hit_at_5"] = any(
                            KnowledgeRetrievalEvaluator._is_disjoint_entity_result(case, chunk) for chunk in chunks[:5]
                        )
                    except Exception as exc:
                        entry["search_refiner_ms"] = round((perf_counter() - start) * 1000, 3)
                        entry["error"] = type(exc).__name__
                    results.append(entry)
    return {
        "schema_version": "knowledge-search-experiment-v1",
        "dataset_version": manifest.dataset_version,
        "repeats": repeats,
        "metric_note": "Document-ID metrics are proxies. strict_metadata_hit_at_5 means any matching metadata hit; evaluator_hit_at_5 also requires complete expected section coverage. Neither establishes clinical correctness.",
        "score_note": "store_score is the production store-returned score; Hybrid normalizes fusion scores before returning them. dense_similarity_score is separate.",
        "adoption_decision": None,
        "warmup_errors": warmup_errors,
        "results": results,
    }


async def run_cli(args, settings=None):
    settings = settings or Config()
    manifest = load_evaluation_manifest(args.evaluation_file).model_copy(
        update={"dataset_version": args.dataset_version.strip()}
    )
    client = create_qdrant_client(settings)
    try:
        distance = (
            models.Distance.DOT
            if settings.KNOWLEDGE_VECTOR_DISTANCE == KnowledgeVectorDistance.DOT
            else models.Distance.COSINE
        )
        fingerprints = await verify_collections(
            client,
            args.dense_collection,
            args.hybrid_collection,
            manifest.dataset_version,
            settings.OPENAI_EMBEDDING_DIMENSIONS,
            distance,
        )
        provider = OpenAIEmbeddingProvider(
            model=settings.OPENAI_EMBEDDING_MODEL,
            dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
            api_key=require_api_key(settings),
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
        )
        common = {
            "client": client,
            "vector_size": settings.OPENAI_EMBEDDING_DIMENSIONS,
            "distance": settings.KNOWLEDGE_VECTOR_DISTANCE,
        }
        stores = {
            "dense": EligibleDenseStore(collection_name=args.dense_collection, **common),
            "hybrid": EligibleHybridStore(
                collection_name=args.hybrid_collection, search_mode=KnowledgeSearchMode.HYBRID, **common
            ),
        }
        report = await compare(manifest, provider, stores, repeats=args.repeats)
        report["collections"] = fingerprints
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        await client.close()


def main():
    args = parse_args()
    report = asyncio.run(run_cli(args))
    print(f"Wrote {len(report['results'])} measured search records to {args.output}")


if __name__ == "__main__":
    main()
