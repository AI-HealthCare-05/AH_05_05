from ai_worker.rag.loaders.csv_loader import CsvLoader


def test_load_cp949_csv(tmp_path) -> None:
    csv_path = tmp_path / "public_data.csv"

    csv_path.write_text(
        "ITEM_SEQ,ITEM_NAME\n"
        "202400001,테스트정\n",
        encoding="cp949",
    )

    rows = CsvLoader().load(csv_path)

    assert len(rows) == 1
    assert rows[0]["ITEM_SEQ"] == "202400001"
    assert rows[0]["ITEM_NAME"] == "테스트정"