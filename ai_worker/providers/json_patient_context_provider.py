import json
from pathlib import Path

from ai_worker.schemas.patient import PatientContext


class JsonPatientContextProvider:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    async def get_patient_context(
        self,
        user_id: int,
        care_episode_id: int,
    ) -> PatientContext:
        with self.file_path.open(encoding="utf-8") as file:
            raw_data = json.load(file)

        patient_context = PatientContext.model_validate(raw_data)

        if patient_context.user_id != user_id:
            raise ValueError("요청한 사용자와 환자 데이터의 사용자가 일치하지 않습니다.")

        if patient_context.care_episode_id != care_episode_id:
            raise ValueError("요청한 케어 ID와 환자 데이터의 케어 ID가 일치하지 않습니다.")

        return patient_context
