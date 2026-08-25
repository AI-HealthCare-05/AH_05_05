from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService


def get_medication_guide_ocr_job_service() -> MedicationGuideOcrJobService:
    return MedicationGuideOcrJobService()
