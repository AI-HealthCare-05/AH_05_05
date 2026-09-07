import asyncio

from ai_worker.schemas.knowledge_ocr import KnowledgeOcrBlock
from ai_worker.services.knowledge_tesseract_ocr_service import (
    KnowledgeOcrFallbackPolicy,
    TesseractKnowledgeOcrProvider,
    TesseractThenFallbackKnowledgeOcrProvider,
)


class FakeTesseractRunner:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[bytes, str, int]] = []

    async def run_tsv(
        self,
        *,
        image_bytes: bytes,
        languages: str,
        page_segmentation_mode: int,
    ) -> str:
        self.calls.append((image_bytes, languages, page_segmentation_mode))
        return self.output


class FakeFallbackProvider:
    name = "fake-clova"
    version = "v2"

    def __init__(self) -> None:
        self.calls = 0

    async def recognize(self, image_bytes: bytes) -> list[KnowledgeOcrBlock]:
        self.calls += 1
        return [
            KnowledgeOcrBlock(
                block_id="fallback-line-1",
                text="CLOVA 복원 결과",
                confidence=0.98,
                bbox={"x0": 1, "top": 2, "x1": 100, "bottom": 20},
                line_break=True,
            )
        ]


def test_tesseract_provider_converts_tsv_lines_to_coordinate_blocks() -> None:
    runner = FakeTesseractRunner(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t96.2\t한글\n"
        "5\t1\t1\t1\t1\t2\t45\t20\t35\t10\t93.8\tEnglish\n"
        "5\t1\t1\t1\t2\t1\t10\t42\t80\t12\t88.0\t다음 줄\n",
    )

    blocks = asyncio.run(TesseractKnowledgeOcrProvider(runner=runner).recognize(b"image-bytes"))

    assert [(block.text, block.confidence, block.line_break) for block in blocks] == [
        ("한글 English", 0.9433, True),
        ("다음 줄", 0.88, True),
    ]
    assert blocks[0].bbox.model_dump() == {
        "x0": 10.0,
        "top": 20.0,
        "x1": 80.0,
        "bottom": 30.0,
    }
    assert runner.calls == [(b"image-bytes", "kor+eng", 3)]


def test_tesseract_provider_keeps_literal_quote_as_ocr_text() -> None:
    """A quote in Tesseract text must not make later TSV rows part of one word."""
    runner = FakeTesseractRunner(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        '5\t1\t1\t1\t1\t1\t10\t20\t10\t10\t96.0\t"\n'
        "5\t1\t1\t1\t2\t1\t10\t42\t40\t10\t96.0\t다음 문장\n",
    )

    blocks = asyncio.run(TesseractKnowledgeOcrProvider(runner=runner).recognize(b"image-bytes"))

    assert [block.text for block in blocks] == ['"', "다음 문장"]


def test_tesseract_result_with_low_confidence_uses_fallback_provider() -> None:
    runner = FakeTesseractRunner(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t40.0\t불확실\n",
    )
    fallback = FakeFallbackProvider()

    blocks = asyncio.run(
        TesseractThenFallbackKnowledgeOcrProvider(
            primary=TesseractKnowledgeOcrProvider(runner=runner),
            fallback=fallback,
            policy=KnowledgeOcrFallbackPolicy(min_average_confidence=0.75),
        ).recognize(b"image-bytes")
    )

    assert [block.text for block in blocks] == ["CLOVA 복원 결과"]
    assert fallback.calls == 1


def test_tesseract_result_above_quality_threshold_skips_fallback_provider() -> None:
    runner = FakeTesseractRunner(
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t94.0\t충분히\n"
        "5\t1\t1\t1\t1\t2\t45\t20\t35\t10\t94.0\t명확한\n"
        "5\t1\t1\t1\t1\t3\t85\t20\t35\t10\t94.0\t문장입니다\n",
    )
    fallback = FakeFallbackProvider()

    blocks = asyncio.run(
        TesseractThenFallbackKnowledgeOcrProvider(
            primary=TesseractKnowledgeOcrProvider(runner=runner),
            fallback=fallback,
            policy=KnowledgeOcrFallbackPolicy(min_average_confidence=0.75),
        ).recognize(b"image-bytes")
    )

    assert [block.text for block in blocks] == ["충분히 명확한 문장입니다"]
    assert fallback.calls == 0
