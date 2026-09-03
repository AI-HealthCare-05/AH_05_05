import json
from pathlib import Path

import pytest
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[3]
IMAGE_ROOT = PROJECT_ROOT / "app/static/images/chatbot"
CSS_ROOT = PROJECT_ROOT / "app/static/css"
ROLES = ("medication", "vitamin", "reminder", "safety", "chat")


@pytest.mark.parametrize("role", ROLES)
def test_doodle_character_formats_are_ready_for_chatbot_use(role: str) -> None:
    stem = IMAGE_ROOT / f"rxvita-doodle-{role}"

    with Image.open(stem.with_suffix(".png")) as image:
        assert image.mode == "RGBA"
        assert image.size == (512, 512)
        assert image.getextrema()[3][0] == 0

    for suffix in (".gif", ".webp"):
        with Image.open(stem.with_suffix(suffix)) as animation:
            assert animation.n_frames >= 24
            assert animation.info["loop"] == 0

    lottie = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
    assert (lottie["w"], lottie["h"]) == (512, 512)
    assert lottie["op"] > lottie["ip"]
    assert lottie["layers"]


def test_doodle_group_and_shared_css_are_available() -> None:
    with Image.open(IMAGE_ROOT / "rxvita-doodle-group.png") as image:
        assert image.mode == "RGBA"
        assert image.size == (1536, 768)
        assert image.getextrema()[3][0] == 0

    assert (CSS_ROOT / "rxvita-chatbot-doodle.css").stat().st_size > 0


def test_clay_medication_character_formats_are_ready_for_chatbot_use() -> None:
    stem = IMAGE_ROOT / "rxvita-clay-medication"

    with Image.open(stem.with_suffix(".png")) as image:
        assert image.mode == "RGBA"
        assert image.size == (512, 512)
        assert image.getextrema()[3][0] == 0

    for suffix in (".gif", ".webp"):
        with Image.open(stem.with_suffix(suffix)) as animation:
            assert animation.n_frames >= 24
            assert animation.info["loop"] == 0

    lottie = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
    assert (lottie["w"], lottie["h"]) == (512, 512)
    assert lottie["op"] > lottie["ip"]
    assert len(lottie["layers"]) == 2
