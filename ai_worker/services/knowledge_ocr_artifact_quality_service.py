import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ai_worker.schemas.knowledge_ocr import KnowledgeOcrDocumentArtifact

_HANGUL_PATTERN = re.compile(r"[가-힣]")
_FRAGMENTED_HANGUL_PATTERN = re.compile(
    r"(?<![가-힣])(?:[가-힣]\s+){2,}[가-힣](?![가-힣])",
)


@dataclass(frozen=True)
class KnowledgeOcrArtifactQualityPolicy:
    min_average_confidence: float = 0.85
    max_fragmented_hangul_ratio: float = 0.1


@dataclass(frozen=True)
class KnowledgeOcrArtifactQualityAssessment:
    average_confidence: float
    fragmented_hangul_ratio: float
    is_eligible: bool


class KnowledgeOcrArtifactQualityService:
    """낮은 품질의 로컬 OCR 결과가 청킹·임베딩으로 이어지는 것을 막습니다."""

    def __init__(
        self,
        *,
        policy: KnowledgeOcrArtifactQualityPolicy | None = None,
    ) -> None:
        self._policy = policy or KnowledgeOcrArtifactQualityPolicy()

    def is_eligible_artifact(self, artifact_path: Path) -> bool:
        try:
            artifact = KnowledgeOcrDocumentArtifact.model_validate_json(
                Path(artifact_path).read_text(encoding="utf-8"),
            )
        except (OSError, ValidationError):
            return False
        return self.assess(artifact).is_eligible

    def assess(
        self,
        artifact: KnowledgeOcrDocumentArtifact,
    ) -> KnowledgeOcrArtifactQualityAssessment:
        blocks = [block for page in artifact.pages for block in page.blocks]
        character_count = sum(len(block.text) for block in blocks)
        average_confidence = sum(block.confidence * len(block.text) for block in blocks) / character_count
        text = "\n".join(block.text for block in blocks)
        hangul_character_count = len(_HANGUL_PATTERN.findall(text))
        fragmented_hangul_count = sum(
            len(_HANGUL_PATTERN.findall(match.group())) for match in _FRAGMENTED_HANGUL_PATTERN.finditer(text)
        )
        fragmented_hangul_ratio = fragmented_hangul_count / hangul_character_count if hangul_character_count else 0.0
        return KnowledgeOcrArtifactQualityAssessment(
            average_confidence=average_confidence,
            fragmented_hangul_ratio=fragmented_hangul_ratio,
            is_eligible=(
                average_confidence >= self._policy.min_average_confidence
                and fragmented_hangul_ratio <= self._policy.max_fragmented_hangul_ratio
            ),
        )
