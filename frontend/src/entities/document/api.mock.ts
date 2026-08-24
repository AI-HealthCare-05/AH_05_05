/**
 * 문서·OCR 목업 데이터.
 *
 * 백엔드가 붙으면 api.ts 의 USE_MOCK 분기와 함께 이 파일만 지우면 됩니다.
 *
 * 값의 기준은 docs/sample-docs 의 환자1(김철수) 문서입니다. 백엔드에서 같은 문서로
 * 테스트할 때 화면과 응답이 어긋나 보이면, 어느 쪽이 틀렸는지 이 파일과 대조하세요.
 *
 * - 진단명·수술명은 의도적으로 OCR 원문 그대로(영문·약어) 둡니다. LLM 단순화 이전
 *   상태를 화면에서 확인하기 위한 것이며, 읽기 좋은 한국어로 바꾸지 않습니다.
 * - medicationDays 는 레코드 전체에 1개 값입니다. 개별 약의 note 에는 "복용 시점"만
 *   담습니다 — O07 약 카드가 "1일 N회 · {note}" 로 조립하므로 note 에 빈도를 다시
 *   넣으면 중복 표시됩니다.
 * - high/medium/low 3단계가 한 화면에 모두 보이도록 신뢰도를 분산했습니다.
 */
import type {
  CapturedDocument,
  ConfirmOcrResultPayload,
  ConfirmOcrResultResponse,
  OcrResult,
  OcrResultReadyStatus,
  OcrStatus,
  UploadDocumentsResult,
} from './types';

const MOCK_BATCH_ID = 'b_mock_9f21';

export function mockUploadDocuments(files: CapturedDocument[]): UploadDocumentsResult {
  return {
    batchId: MOCK_BATCH_ID,
    documentIds: files.map((_, i) => 101 + i),
    ocrStatus: 'processing',
  };
}

/**
 * **목업 전용 규칙.** batchId 문자열로 ocrStatus 를 갈라, 결과 필드가 없는 상태
 * (queued·processing·failed·cancelled)와 complete 를 화면에서 눌러볼 수 있게 합니다.
 * 실서버는 batchId 로 상태를 정하지 않습니다.
 *
 * entities/chat/api.mock.ts 의 shouldAnswerWithoutSources 와 같은 방식입니다 —
 * 별도 플래그·파일 없이 화면에서 도달할 수 있는 값으로 분기합니다.
 *
 *   navigate('/dev/ocr-review', { state: { batchId: 'failed-1' } })
 */
// ready_for_review 는 기본 경로라 표에 넣지 않습니다. 타입으로 그걸 강제합니다.
const STATUS_BY_BATCH_ID: Array<{
  match: string;
  status: Exclude<OcrStatus, OcrResultReadyStatus> | 'complete';
}> = [
  { match: 'processing', status: 'processing' },
  { match: 'queued', status: 'queued' },
  { match: 'failed', status: 'failed' },
  { match: 'cancelled', status: 'cancelled' },
  { match: 'complete', status: 'complete' },
];

export function mockOcrResult(batchId: string): OcrResult {
  const forced = STATUS_BY_BATCH_ID.find((r) => batchId.includes(r.match));
  // 결과 필드가 없는 상태는 명세 4번대로 { batchId, ocrStatus } 만 돌려줍니다.
  if (forced && forced.status !== 'complete') {
    return { batchId, ocrStatus: forced.status };
  }

  return {
    batchId,
    // complete 는 결과 필드가 있는 상태라 아래 값을 그대로 쓰되 상태만 갈아끼웁니다.
    ocrStatus: forced?.status === 'complete' ? 'complete' : 'ready_for_review',
    fields: {
      diagnosis: { value: 'Rt Femur head Fracture, closed', confidence: 'low' },
      surgery: { value: 'Rt Femur head ORIF', confidence: 'low' },
      dischargeDate: { value: '2026-08-07', confidence: 'high' },
      medicationDays: { value: 14, confidence: 'low' },
    },
    medications: [
      { tempId: 'm1', name: 'Celecoxib', dose: '200mg', timesPerDay: 2, note: '아침·저녁 식후', confidence: 'high' },
      { tempId: 'm2', name: 'Rivaroxaban', dose: '10mg', timesPerDay: 1, note: '저녁 식후', confidence: 'low' },
      { tempId: 'm3', name: 'Acetaminophen', dose: '650mg', timesPerDay: null, note: '필요 시, 6시간 이상 간격', confidence: 'high' },
      { tempId: 'm4', name: 'Famotidine', dose: '20mg', timesPerDay: 2, note: '아침·저녁 식후', confidence: 'medium' },
    ],
    advices: [
      { tempId: 'a1', text: '보행기 사용', confidence: 'high' },
      { tempId: 'a2', text: '계단과 쪼그려 앉기 피하기', confidence: 'medium' },
    ],
    // 낮은 신뢰도: 진단명 + 수술명 + medicationDays + Rivaroxaban = 4건
    lowConfidenceCount: 4,
  };
}

/** hasMedication 은 보낸 약 개수에 따라 달라지므로 여기서 계산합니다(O06 변형 대응). */
export function mockConfirmOcrResult(payload: ConfirmOcrResultPayload): ConfirmOcrResultResponse {
  return {
    recordId: 12,
    hasMedication: payload.medications.length > 0,
    statusCode: 'active',
  };
}
