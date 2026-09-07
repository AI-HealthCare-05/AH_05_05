from __future__ import annotations

import asyncio
import csv
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from ai_worker.schemas.knowledge_ocr import KnowledgeOcrBlock, KnowledgeOcrBoundingBox


class TesseractCommandRunner(Protocol):
    async def run_tsv(
        self,
        *,
        image_bytes: bytes,
        languages: str,
        page_segmentation_mode: int,
    ) -> str: ...


class SubprocessTesseractCommandRunner:
    """로컬 Tesseract CLI만 호출하고 이미지나 OCR 본문을 파일로 남기지 않습니다."""

    async def run_tsv(
        self,
        *,
        image_bytes: bytes,
        languages: str,
        page_segmentation_mode: int,
    ) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "tesseract",
                "stdin",
                "stdout",
                "-l",
                languages,
                "--psm",
                str(page_segmentation_mode),
                "tsv",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "로컬 Tesseract가 없습니다. Tesseract와 kor 언어팩을 설치하세요."
            ) from error
        stdout, stderr = await process.communicate(image_bytes)
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Tesseract OCR 실행에 실패했습니다: {message}")
        return stdout.decode("utf-8", errors="replace")


class TesseractKnowledgeOcrProvider:
    """Tesseract TSV의 단어 좌표를 기존 OCR block 계약으로 변환합니다."""

    name = "tesseract-local-ocr"
    version = "tsv-kor-eng-psm3-v1"

    def __init__(
        self,
        *,
        runner: TesseractCommandRunner | None = None,
        languages: str = "kor+eng",
        page_segmentation_mode: int = 3,
    ) -> None:
        self._runner = runner or SubprocessTesseractCommandRunner()
        self._languages = languages
        self._page_segmentation_mode = page_segmentation_mode

    async def recognize(self, image_bytes: bytes) -> list[KnowledgeOcrBlock]:
        tsv = await self._runner.run_tsv(
            image_bytes=image_bytes,
            languages=self._languages,
            page_segmentation_mode=self._page_segmentation_mode,
        )
        return self._parse_tsv(tsv)

    @staticmethod
    def _parse_tsv(tsv: str) -> list[KnowledgeOcrBlock]:
        words_by_line: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
        for row in csv.DictReader(tsv.splitlines(), delimiter="\t"):
            text = (row.get("text") or "").strip()
            confidence = TesseractKnowledgeOcrProvider._confidence(row.get("conf"))
            if row.get("level") != "5" or not text or confidence is None:
                continue
            line_key = tuple(
                row.get(field, "")
                for field in ("page_num", "block_num", "par_num", "line_num")
            )
            words_by_line[line_key].append(row)

        blocks: list[KnowledgeOcrBlock] = []
        for line_key, words in words_by_line.items():
            coordinates = [
                TesseractKnowledgeOcrProvider._coordinates(word)
                for word in words
            ]
            if any(coordinate is None for coordinate in coordinates):
                continue
            valid_coordinates = [coordinate for coordinate in coordinates if coordinate is not None]
            weights = [max(len(word["text"].strip()), 1) for word in words]
            confidences = [
                TesseractKnowledgeOcrProvider._confidence(word.get("conf"))
                for word in words
            ]
            blocks.append(
                KnowledgeOcrBlock(
                    block_id="tesseract-" + "-".join(line_key),
                    text=" ".join(word["text"].strip() for word in words),
                    confidence=round(
                        sum(
                            confidence * weight
                            for confidence, weight in zip(confidences, weights, strict=True)
                            if confidence is not None
                        )
                        / sum(weights),
                        4,
                    ),
                    bbox=KnowledgeOcrBoundingBox(
                        x0=min(coordinate[0] for coordinate in valid_coordinates),
                        top=min(coordinate[1] for coordinate in valid_coordinates),
                        x1=max(coordinate[2] for coordinate in valid_coordinates),
                        bottom=max(coordinate[3] for coordinate in valid_coordinates),
                    ),
                    line_break=True,
                )
            )
        return blocks

    @staticmethod
    def _confidence(raw_confidence: str | None) -> float | None:
        try:
            value = float(raw_confidence or "")
        except ValueError:
            return None
        if value < 0:
            return None
        return min(value / 100, 1.0)

    @staticmethod
    def _coordinates(row: dict[str, str]) -> tuple[float, float, float, float] | None:
        try:
            left = float(row["left"])
            top = float(row["top"])
            width = float(row["width"])
            height = float(row["height"])
        except (KeyError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return (left, top, left + width, top + height)


@dataclass(frozen=True)
class KnowledgeOcrFallbackPolicy:
    min_average_confidence: float = 0.75
    min_text_characters: int = 12

    def requires_fallback(self, blocks: list[KnowledgeOcrBlock]) -> bool:
        if not blocks:
            return True
        character_count = sum(len(block.text) for block in blocks)
        if character_count < self.min_text_characters:
            return True
        weighted_confidence = sum(
            block.confidence * len(block.text) for block in blocks
        ) / character_count
        return weighted_confidence < self.min_average_confidence


class TesseractThenFallbackKnowledgeOcrProvider:
    """로컬 OCR 품질이 낮은 페이지만 대체 OCR 공급자에 전달합니다."""

    name = "tesseract-local-first-with-fallback"
    version = "v1"

    def __init__(
        self,
        *,
        primary: TesseractKnowledgeOcrProvider,
        fallback,
        policy: KnowledgeOcrFallbackPolicy | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._policy = policy or KnowledgeOcrFallbackPolicy()

    async def recognize(self, image_bytes: bytes) -> list[KnowledgeOcrBlock]:
        blocks = await self._primary.recognize(image_bytes)
        if not self._policy.requires_fallback(blocks):
            return blocks
        return await self._fallback.recognize(image_bytes)
