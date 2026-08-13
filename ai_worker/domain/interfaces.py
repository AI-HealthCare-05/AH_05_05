#구현체 교체를 위한 인터페이스(각 기능이 어떤 입력을 받고 어떤 결과를 반환해야 하는지 정의한 계약서)

from typing import Protocol

from ai_worker.schemas.guide import RecoveryGuideResult
from ai_worker.schemas.patient import PatientContext
from ai_worker.schemas.public_data import RetrievedPublicChunk
from ai_worker.schemas.safety import SafetyResult


class PatientContextProvider(Protocol): #환자 데이터 조회기
    async def get_patient_context(
        self,
        user_id: int,
        care_episode_id: int,
    ) -> PatientContext:
        ...


class PublicDataRetriever(Protocol): #공공데이터/RAG 검색기
    async def search(
        self,
        patient_context: PatientContext,
        limit: int = 5,
    ) -> list[RetrievedPublicChunk]:
        ...


class GuideGenerator(Protocol):#회복 안내서 생성기
    async def generate(
        self,
        patient_context: PatientContext,
        public_chunks: list[RetrievedPublicChunk],
    ) -> RecoveryGuideResult:
        ...


class OutputSafetyValidator(Protocol): #최종 출력 안전성 검색기
    async def validate(
        self,
        patient_context: PatientContext,
        result: RecoveryGuideResult,
    ) -> SafetyResult:
        ...