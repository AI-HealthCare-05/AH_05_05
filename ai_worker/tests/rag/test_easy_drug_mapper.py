from ai_worker.rag.mappers.easy_drug_mapper import (
    EasyDrugDocumentMapper,
)


def test_map_easy_drug_row() -> None:
    row = {
        "ITEM_SEQ": "202400001",
        "ITEM_NAME": "테스트정",
        "EFCY_QESITM": "<p>피로 회복에 사용합니다.</p>",
        "USE_METHOD_QESITM": "<p>1일 1회 복용합니다.</p>",
        "ATPN_WARN_QESITM": "",
        "ATPN_QESITM": "",
        "INTRC_QESITM": "",
        "SE_QESITM": "",
        "DEPOSIT_METHOD_QESITM": "",
    }

    documents = EasyDrugDocumentMapper().map_row(row)

    assert len(documents) == 2
    assert documents[0].metadata.chunk_type == "EFFECT"
    assert documents[1].metadata.chunk_type == "USAGE"
    assert "<p>" not in documents[0].content
    assert documents[0].metadata.source_record_key == "202400001"