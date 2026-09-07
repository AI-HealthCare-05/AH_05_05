import json

import pytest

from scripts import validate_preprocess_memory_v34 as subject


def test_cached_failed_memory_gate_cannot_turn_into_success(tmp_path, monkeypatch):
    output = tmp_path / "memory.json"
    monkeypatch.setattr(subject, "_code_identity", lambda: {"test": "fixed"})
    monkeypatch.setattr(subject.sys, "argv", ["validate", "--output", str(output)])
    identity = {
        "code": {"test": "fixed"},
        "harnessSha256": subject.hashlib.sha256(subject.Path(subject.__file__).read_bytes()).hexdigest(),
    }
    runs = [
        {"version": version, "peakWorkingSetBytes": peak, "roundtripPassed": True, "ocrCalls": 0}
        for version, peak in (("v3.1.3", 100), ("v3.4.1", 200))
    ]
    output.write_text(
        json.dumps(
            {
                "identity": subject.digest(identity),
                "runs": runs,
                "checksum": subject.digest(runs),
                "memoryGatePassed": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="memory"):
        subject.main()

