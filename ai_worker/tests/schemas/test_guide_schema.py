import pytest
from pydantic import ValidationError

from ai_worker.schemas.guide import (
    RecoveryGuideContent,
)


def test_recovery_guide_content_labels_ai_generated_lifestyle() -> None:
    content = RecoveryGuideContent(
        lifestyle_guide=[
            "충분히 쉬고 무리하지 마세요."
        ],
        safety_notice=(
            "이 안내는 의료진의 진료를 "
            "대체하지 않습니다."
        ),
    )

    assert (
        content.lifestyle_guide_label
        == "AI 생성 일반 안내"
    )

def test_recovery_guide_content_rejects_invalid_lifestyle_label() -> None:
    with pytest.raises(ValidationError):
        RecoveryGuideContent(
            lifestyle_guide_label=(
                "공공자료 기반 안내"
            ),
            lifestyle_guide=[
                "충분히 쉬세요."
            ],
            safety_notice=(
                "이 안내는 의료진의 진료를 "
                "대체하지 않습니다."
            ),
        )
