from pathlib import Path

from ai_worker.schemas.guideline_manifest import (
    GuidelineManifest,
)


class GuidelineManifestLoader:
    def load(
        self,
        manifest_path: Path,
    ) -> GuidelineManifest:
        path = Path(manifest_path)

        manifest = GuidelineManifest.model_validate_json(path.read_text(encoding="utf-8"))

        resolved_documents = [
            document.model_copy(
                update={
                    "file_path": self._resolve_file_path(
                        manifest_path=path,
                        file_path=document.file_path,
                    )
                }
            )
            for document in manifest.documents
        ]

        for document in resolved_documents:
            if not document.file_path.is_file():
                raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {document.file_path}")

        return manifest.model_copy(
            update={
                "documents": resolved_documents,
            }
        )

    @staticmethod
    def _resolve_file_path(
        *,
        manifest_path: Path,
        file_path: Path,
    ) -> Path:
        if file_path.is_absolute():
            return file_path.resolve()

        return (manifest_path.parent / file_path).resolve()
