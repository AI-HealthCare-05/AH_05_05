from pathlib import Path

from pydantic import ValidationError

from ai_worker.schemas.knowledge import KnowledgeChunk


class KnowledgeChunkLoader:
    def load(
        self,
        directory: Path,
        expected_dataset_version: str,
    ) -> list[KnowledgeChunk]:
        normalized_version = expected_dataset_version.strip()
        if not normalized_version:
            raise ValueError("기대 dataset_version은 비어 있을 수 없습니다.")

        paths = sorted(directory.glob("*.jsonl"))
        if not paths:
            raise ValueError(f"청크 JSONL 파일을 찾을 수 없습니다: {directory}")

        chunks: list[KnowledgeChunk] = []
        seen_chunk_ids: set[str] = set()
        release_versions: set[str] = set()

        for path in paths:
            for line_number, raw_line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                line = raw_line.strip()
                if not line:
                    continue
                chunk = self._parse_chunk(
                    line=line,
                    path=path,
                    line_number=line_number,
                )
                if not chunk.metadata.index_eligible:
                    raise ValueError(f"인덱싱 대상이 아닌 청크가 release에 포함되었습니다: {path}:{line_number}")
                if chunk.chunk_id in seen_chunk_ids:
                    raise ValueError(
                        f"중복 chunk_id가 release에 포함되었습니다: {chunk.chunk_id} ({path}:{line_number})"
                    )
                seen_chunk_ids.add(chunk.chunk_id)
                release_versions.add(chunk.metadata.dataset_version)
                chunks.append(chunk)

        if not chunks:
            raise ValueError(f"청크 JSONL에 유효한 청크가 없습니다: {directory}")
        if release_versions != {normalized_version}:
            versions = ", ".join(sorted(release_versions))
            raise ValueError(
                "release의 dataset_version이 기대값과 일치하지 않습니다: "
                f"expected={normalized_version}, actual={versions}"
            )

        return chunks

    @staticmethod
    def _parse_chunk(
        *,
        line: str,
        path: Path,
        line_number: int,
    ) -> KnowledgeChunk:
        try:
            return KnowledgeChunk.model_validate_json(line)
        except ValidationError as error:
            raise ValueError(f"KnowledgeChunk JSON 검증에 실패했습니다: {path}:{line_number}") from error
