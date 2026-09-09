from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.db.reference_seed import (
    ReferenceSeedError,
    decode_seed_value,
    encode_seed_value,
    validate_seed_artifacts,
)


def test_manifest_rejects_unknown_table(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        '{"version":"v1","schema_head":"42","batch_size":500,'
        '"tables":[{"name":"users","file":"users.jsonl.gz","row_count":0,'
        '"sha256":"0000000000000000000000000000000000000000000000000000000000000000",'
        '"key_fields":["id"]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ReferenceSeedError, match="허용되지 않은 테이블"):
        validate_seed_artifacts(tmp_path)


def test_manifest_rejects_checksum_mismatch(tmp_path: Path) -> None:
    import gzip

    seed_path = tmp_path / "badges.jsonl.gz"
    with gzip.open(seed_path, "wt", encoding="utf-8") as stream:
        stream.write('{"name":"걷기 배지"}\n')
    (tmp_path / "manifest.json").write_text(
        '{"version":"v1","schema_head":"42","batch_size":500,'
        '"tables":[{"name":"badges","file":"badges.jsonl.gz","row_count":1,'
        '"sha256":"0000000000000000000000000000000000000000000000000000000000000000",'
        '"key_fields":["name"]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ReferenceSeedError, match="checksum"):
        validate_seed_artifacts(tmp_path)


def test_seed_codec_round_trips_supported_scalars() -> None:
    values = [
        Decimal("1.250"),
        datetime(2026, 9, 9, 12, 30),
        date(2026, 9, 9),
        None,
        "문자열",
        7,
        True,
    ]

    assert [decode_seed_value(encode_seed_value(value)) for value in values] == values
