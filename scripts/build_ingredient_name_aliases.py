"""말뭉치의 한/영 병기에서 성분명 별칭 사전을 만든다.

지식베이스 본문에는 `와파린(warfarin)`처럼 한글 성분명과 영문명이 함께 적힌 구간이 있다.
그 병기에서 후보를 뽑고, 한글 쪽이 `interaction_entities` 카탈로그와 정확히 일치할 때만
채택한다. 카탈로그 검증이 없으면 `아스피린` 대신 `은 저위험 환자에게서 아스피린` 같은
앞 문장 꼬리가 그대로 들어온다.

사람이 항목을 쓰지 않는다. 말뭉치와 카탈로그가 바뀌면 다시 생성한다.

사용: uv run python scripts/build_ingredient_name_aliases.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import AsyncQdrantClient
from tortoise import Tortoise

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_worker.core.config import Config  # noqa: E402
from app.core.db.databases import TORTOISE_ORM  # noqa: E402

OUTPUT_PATH = PROJECT_ROOT / "ai_worker" / "rag" / "data" / "ingredient_name_aliases.json"
SCROLL_BATCH = 2000

# `한글(english)` 병기.
_BILINGUAL = re.compile(r"([가-힣]{2,20})\s*\(\s*([A-Za-z][A-Za-z0-9\-' ]{2,30})\s*\)")
_MIN_ENGLISH_LENGTH = 3
# 한 번만 등장한 병기는 원문 오타·규격 표기를 그대로 들여온다.
# 실측: `로바스타틴(atrovastatin)`, `시메티콘(usp)`, `헤파린(lmwh)`이 모두 1회 등장이다.
_MIN_OCCURRENCES = 2


def _normalize_english(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _catalog_match(korean: str, catalog: set[str]) -> str | None:
    """포착한 한글이 카탈로그 성분명과 통째로 일치할 때만 채택한다.

    앞에서 한 글자씩 깎아 맞추면 카탈로그에 없는 이름이 다른 물질로 절단된다.
    실측: `공황(panic)`→`황`, `대황(rheum palmatum)`→`황`,
    `클로르펜터민(chlorphentermine)`→`펜터민`. 없는 근거를 만드는 경로다.
    """
    if korean.casefold() in catalog:
        return korean
    return None


async def _load_catalog() -> set[str]:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        connection = Tortoise.get_connection("default")
        rows = await connection.execute_query_dict("SELECT normalized_name FROM interaction_entities")
        return {row["normalized_name"] for row in rows if row["normalized_name"]}
    finally:
        await Tortoise.close_connections()


async def _collect_aliases(
    *,
    settings: Config,
    catalog: set[str],
) -> tuple[dict[str, Counter], int, int]:
    client = AsyncQdrantClient(url=settings.QDRANT_URL, timeout=settings.QDRANT_TIMEOUT_SECONDS)
    candidates: dict[str, Counter] = {}
    chunk_count = 0
    raw_count = 0
    try:
        offset = None
        while True:
            points, offset = await client.scroll(
                collection_name=settings.KNOWLEDGE_QDRANT_COLLECTION,
                limit=SCROLL_BATCH,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                chunk_count += 1
                content = str(point.payload.get("content", ""))
                for korean, english in _BILINGUAL.findall(content):
                    raw_count += 1
                    normalized_english = _normalize_english(english)
                    if len(normalized_english) < _MIN_ENGLISH_LENGTH:
                        continue
                    matched = _catalog_match(korean.strip(), catalog)
                    if matched is None:
                        continue
                    candidates.setdefault(normalized_english, Counter())[matched] += 1
            if offset is None:
                break
    finally:
        await client.close()
    return candidates, chunk_count, raw_count


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력한다")
    args = parser.parse_args()

    settings = Config()
    catalog = await _load_catalog()
    candidates, chunk_count, raw_count = await _collect_aliases(settings=settings, catalog=catalog)

    accepted = {
        english: counter.most_common(1)[0]
        for english, counter in sorted(candidates.items())
        if counter.most_common(1)[0][1] >= _MIN_OCCURRENCES
    }
    aliases = {english: korean for english, (korean, _) in accepted.items()}
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source_collection": settings.KNOWLEDGE_QDRANT_COLLECTION,
        "scanned_chunk_count": chunk_count,
        "bilingual_match_count": raw_count,
        "catalog_entity_count": len(catalog),
        "minimum_occurrences": _MIN_OCCURRENCES,
        # 사람이 항목을 쓰지는 않지만, 몇 번 관측됐는지는 검토할 수 있어야 한다.
        "occurrences": {english: count for english, (_, count) in accepted.items()},
        "aliases": aliases,
    }

    print(f"말뭉치 {chunk_count}청크 · 병기 {raw_count}건 · 카탈로그 {len(catalog)}종")
    print(f"후보 {len(candidates)}종 → 채택 {len(aliases)}종 (최소 관측 {_MIN_OCCURRENCES}회)")
    for english, korean in list(aliases.items())[:10]:
        print(f"  {english:28} → {korean}")
    if args.dry_run:
        print("\n--dry-run: 파일을 쓰지 않았다")
        return
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n저장: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
