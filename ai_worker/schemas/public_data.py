#Vector DB에서 검색한 공공데이터 모트

from pydantic import BaseModel


class PublicDataMetadata(BaseModel): #공공 데이터 메타 데이터
    #데이터셋 및 레코드 식별
    dataset_key: str
    dataset_version: str | None = None
    source_record_key: str | None = None
    source_field: str | None = None
    chunk_type: str | None = None

    #의약품/ 도메인 정보
    product_name: str | None = None
    ingredient_name: str | None = None


    #출처 및 출처 검증 정보
    source_title: str | None = None
    source_organization: str | None = None
    source_url: str | None = None


class RetrievedPublicChunk(BaseModel): #검색된 공공데이터 청크 단위(Vector DB에서 검색 이후결과)
    vector_chunk_id: str
    content: str
    similarity_score: float | None = None
    metadata: PublicDataMetadata

class PublicDataDocument(BaseModel): #VectorDb에 넣기 전 문서
    content: str
    metadata: PublicDataMetadata