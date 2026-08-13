// REQ-DOC-001 / 노션 API 명세 3-1, 3-2, 3-3 기준 타입

export type UploadPurpose = 'initial' | 'reupload';

export type OcrStatus = 'pending' | 'processing' | 'done' | 'partial_failed' | 'failed';

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

export interface OcrResult {
  batchId: string;
  ocrStatus: OcrStatus;
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
