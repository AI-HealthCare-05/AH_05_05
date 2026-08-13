import csv
from pathlib import Path


class CsvLoader:
    def __init__(self, encoding: str = "cp949") -> None:
        self.encoding = encoding

    def load(self, file_path: Path) -> list[dict[str, str]]:
        with file_path.open(
            encoding=self.encoding,
            newline="",
        ) as file:
            reader = csv.DictReader(file)

            if reader.fieldnames is None:
                raise ValueError("CSV 헤더가 없습니다.")

            return [
                {
                    key: (value or "").strip()
                    for key, value in row.items()
                    if key is not None
                }
                for row in reader
            ]