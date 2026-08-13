import html
import re

from ai_worker.schemas.public_data import (
    PublicDataDocument,
    PublicDataMetadata,
)


class EasyDrugDocumentMapper:
    FIELD_MAP = {
        "EFCY_QESITM": ("EFFECT", "효능·효과"),
        "USE_METHOD_QESITM": ("USAGE", "사용 방법"),
        "ATPN_WARN_QESITM": ("WARNING", "중요 경고"),
        "ATPN_QESITM": ("PRECAUTION", "주의사항"),
        "INTRC_QESITM": ("INTERACTION", "상호작용"),
        "SE_QESITM": ("SIDE_EFFECT", "이상반응"),
        "DEPOSIT_METHOD_QESITM": ("STORAGE", "보관 방법"),
    }

    def __init__(self, dataset_version: str = "2024") -> None:
        self.dataset_version = dataset_version

    def map_row(
        self,
        row: dict[str, str],
    ) -> list[PublicDataDocument]:
        item_seq = row.get("ITEM_SEQ", "").strip()
        item_name = row.get("ITEM_NAME", "").strip()

        if not item_seq or not item_name:
            raise ValueError("ITEM_SEQ와 ITEM_NAME은 필수입니다.")

        documents: list[PublicDataDocument] = []

        for source_field, (
            chunk_type,
            section_name,
        ) in self.FIELD_MAP.items():
            text = self._clean_html(row.get(source_field, ""))

            if not text:
                continue

            documents.append(
                PublicDataDocument(
                    content=f"{item_name} - {section_name}: {text}",
                    metadata=PublicDataMetadata(
                        dataset_key="MFDS_EASY_DRUG",
                        dataset_version=self.dataset_version,
                        source_record_key=item_seq,
                        source_field=source_field,
                        chunk_type=chunk_type,
                        product_name=item_name,
                        source_title=item_name,
                        source_organization="식품의약품안전처",
                    ),
                )
            )

        return documents

    @staticmethod
    def _clean_html(value: str) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", value or "")
        return " ".join(
            html.unescape(without_tags).split()
        )