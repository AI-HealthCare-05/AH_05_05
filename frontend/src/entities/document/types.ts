// REQ-DOC-001 / 노션 API 명세 3-1, 3-2, 3-3 기준 타입

export type UploadPurpose = 'initial' | 'reupload';

/**
 * OCR 작업 상태. ERD `Enum ocr_job_status` · 노션 API 명세 4번과 같은 집합입니다.
 *
 * **응답 표기(소문자)를 따릅니다.** DB Enum 은 대문자지만 프론트는 API 응답을 그대로 받습니다.
 *
 * `ready_for_review` 가 결과를 보여줄 수 있는 상태입니다 — 검토 화면(07)을 여는 조건.
 * `queued`·`processing` 에서는 명세 4번대로 결과 필드가 오지 않으므로, 결과를 읽기 전에
 * 상태부터 갈라야 합니다.
 */
export type OcrStatus =
  | 'queued'
  | 'processing'
  | 'ready_for_review'
  | 'complete'
  | 'failed'
  | 'cancelled';

export type Confidence = 'high' | 'medium' | 'low';

export interface UploadDocumentsResult {
  batchId: string;
  documentIds: number[];
  ocrStatus: OcrStatus;
}

export interface OcrField<T> {
  value: T | null;
  confidence: Confidence;
}

export interface OcrMedication {
  tempId: string;
  name: string;
  dose: string;
  timesPerDay: number | null;
  /** 약봉투에 적힌 약별 처방 일수. 읽히지 않으면 null입니다. */
  days: number | null;
  /** 복용 시점 원문. 예: "아침·저녁 식후", "필요 시" */
  note: string;
  /**
   * O07(복약 정보 편집 모달)에서 사용자가 새로 추가한 약은 OCR로 추출된 값이
   * 아니므로 신뢰도가 없습니다(값이 있으면 = OCR 추출 항목, 없으면 = 사용자 추가 항목).
   */
  confidence?: Confidence;
}

/** 결과 필드가 오는 상태. 명세 4번은 이 두 상태에서만 fields·medications 를 보냅니다. */
export type OcrResultReadyStatus = 'ready_for_review' | 'complete';

/**
 * 결과 필드가 없는 상태 — queued · processing · failed · cancelled.
 * 진행 중이라 아직 없거나(queued·processing), 읽어낸 결과가 없어서(failed·cancelled)
 * 응답이 `{ batchId, ocrStatus }` 두 개뿐입니다.
 */
interface OcrResultPending {
  batchId: string;
  ocrStatus: Exclude<OcrStatus, OcrResultReadyStatus>;
}

interface OcrResultReady {
  batchId: string;
  ocrStatus: OcrResultReadyStatus;
  fields: {
    /** 약봉투 조제일. 미래 날짜일 수 없습니다. */
    dispensedDate: OcrField<string>;
  };
  medications: OcrMedication[];
  lowConfidenceCount: number;
}

/**
 * 상태에 따라 결과 필드 유무가 갈립니다(명세 4번).
 *
 * **판별 유니온으로 둔 이유는 `ocrStatus` 를 먼저 검사하지 않으면 `fields` 에 접근할 수
 * 없게 만들기 위해서입니다.** `fields?:` optional 로 두면 물음표를 빠뜨린 자리를 타입이
 * 잡아주지 못하고, 목업이 항상 값을 채워주는 탓에 실 API 를 붙이는 순간에야 드러납니다.
 */
export type OcrResult = OcrResultPending | OcrResultReady;

export interface ConfirmOcrResultPayload {
  dispensedDate: string;
  medications: Array<{
    tempId: string;
    name: string;
    dose: string;
    timesPerDay: number | null;
    days: number | null;
    note: string;
  }>;
}

export interface ConfirmOcrResultResponse {
  recordId: number;
  hasMedication: boolean;
  statusCode: 'pending' | 'active';
}
