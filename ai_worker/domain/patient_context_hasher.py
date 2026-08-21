import hashlib
import json

from ai_worker.schemas.patient import (
    PatientContext,
)


def resolve_patient_context_hash(
    patient_context: PatientContext,
) -> str:
    """환자 확정 해시를 반환하거나 입력 내용으로 생성한다."""

    if patient_context.confirmation_hash:
        return patient_context.confirmation_hash

    payload = patient_context.model_dump(
        mode="json",
        exclude={
            "confirmation_hash",
        },
    )

    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )

    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
