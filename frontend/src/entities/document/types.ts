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

/** 카메라 루프·갤러리 선택으로 아직 서버에 올리기 전, 화면에서 들고 있는 문서 1장. */
export interface CapturedDocument {
  id: string;
  fileName: string;
  /** 갤러리로 고른 경우에만 채워집니다. 카메라 촬영은 크기를 알 수 없다고 가정합니다. */
  sizeLabel?: string;
}

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
  /**
   * 스펙(3-2)에는 약별 복용일수 필드가 없습니다. 복용일수는 fields.medicationDays
   * 하나로만 관리하기로 확인했고, 개별 약의 "며칠분"은 필요하면 이 note 텍스트에
   * 자연어로 녹여 넣습니다(예: "1일 2회 · 7일분"). 별도 구조화 필드를 추가하지 않습니다.
   */
  note: string;
  /**
   * O07(복약 정보 편집 모달)에서 사용자가 새로 추가한 약은 OCR로 추출된 값이
   * 아니므로 신뢰도가 없습니다(값이 있으면 = OCR 추출 항목, 없으면 = 사용자 추가 항목).
   */
  confidence?: Confidence;
}

export interface OcrAdvice {
  tempId: string;
  text: string;
  confidence: Confidence;
}

/** 결과 필드가 오는 상태. 명세 4번은 이 두 상태에서만 fields·medications·advices 를 보냅니다. */
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
    diagnosis: OcrField<string>;
    /**
     * 노션 API 명세 3-2에는 없는 필드입니다. Figma `07` 프레임에도 진단명만 있고
     * 수술명은 없었으나, 실제로는 진단명과 수술명이 별개 값으로 필요하다고 판단해
     * (사용자 확인 후) 타입과 Figma 양쪽에 함께 추가했습니다.
     */
    surgery: OcrField<string>;
    dischargeDate: OcrField<string>;
    /** 처방 복용일수. 레코드 전체에 하나뿐인 값이며(스펙 3-2 기준), 개별 약마다는 없습니다. */
    medicationDays: OcrField<number>;
  };
  medications: OcrMedication[];
  advices: OcrAdvice[];
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
  diagnosis: string;
  surgery: string;
  dischargeDate: string;
  medicationDays: number;
  medications: Array<{
    tempId: string;
    name: string;
    dose: string;
    timesPerDay: number | null;
    note: string;
  }>;
  advices: Array<{ tempId: string; text: string }>;
}

export interface ConfirmOcrResultResponse {
  recordId: number;
  hasMedication: boolean;
  statusCode: 'pending' | 'active';
}
