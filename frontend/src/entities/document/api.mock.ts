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
 * - days 는 약별 처방 일수이고 administration 은 복용 방법 원문입니다.
 * - high 항목은 배지를 숨기고 리바록사반 low 한 건만 확인 대상으로 보이게 합니다.
 */
import type {
  ConfirmOcrResultPayload,
  ConfirmOcrResultResponse,
  OcrResult,
  OcrResultReadyStatus,
  OcrStatus,
  UploadDocumentsResult,
} from './types';

let uploadSequence = 0;
const uploadedBatchPollCount = new Map<string, number>();

export function mockUploadDocument(file: File): UploadDocumentsResult {
  if (file.name.includes('upload-fail')) {
    throw new Error('사진을 올리지 못했어요. 연결을 확인하고 다시 시도해주세요.');
  }
  uploadSequence += 1;
  const batchId = `b_mock_uploaded_${uploadSequence}`;
  const documentId = 100 + uploadSequence;
  // 실계약과 같이 후속 조회 키는 batchId가 아니라 documentIds[0]입니다.
  uploadedBatchPollCount.set(String(documentId), 0);
  return {
    batchId,
    documentIds: [documentId],
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
  const uploadedPollCount = uploadedBatchPollCount.get(batchId);
  if (uploadedPollCount !== undefined && uploadedPollCount < 2) {
    uploadedBatchPollCount.set(batchId, uploadedPollCount + 1);
    return {
      batchId,
      ocrStatus: uploadedPollCount === 0 ? 'queued' : 'processing',
    };
  }
  const forced = STATUS_BY_BATCH_ID.find((r) => batchId.includes(r.match));
  if (forced?.status === 'failed') {
    return { batchId, ocrStatus: 'failed', errorCode: 'EXTRACTION_FAILED' };
  }
  // 진행 중·취소 상태에는 결과 필드가 없습니다.
  if (forced && forced.status !== 'complete') {
    return { batchId, ocrStatus: forced.status };
  }

  return {
    batchId,
    // complete 는 결과 필드가 있는 상태라 아래 값을 그대로 쓰되 상태만 갈아끼웁니다.
    ocrStatus: forced?.status === 'complete' ? 'complete' : 'ready_for_review',
    documentImageUrl: '/mock/medication-envelope.svg',
    fields: {
      dispensedDate: { value: '2026-08-22', confidence: 'high' },
    },
    medications: [
      { tempId: 'm1', name: '셀레콕시브', dose: '200mg', efficacy: '염증과 통증 완화', administration: '아침·저녁 식후', precautions: '위장장애가 있으면 상담하세요.', timesPerDay: 2, days: 7, confidence: 'high' },
      { tempId: 'm2', name: '리바록사반', dose: '10mg', efficacy: '혈전 생성 억제', administration: '아침·저녁 식후', precautions: '출혈 증상이 있으면 상담하세요.', timesPerDay: 2, days: 7, confidence: 'low' },
      { tempId: 'm3', name: '아세트아미노펜', dose: '650mg', efficacy: '해열 및 진통', administration: '필요 시, 6시간 이상 간격', precautions: '과량 복용하지 마세요.', timesPerDay: null, days: 7, confidence: 'high' },
      { tempId: 'm4', name: '파모티딘', dose: '20mg', efficacy: '위산 분비 억제', administration: '아침·저녁 식후', precautions: '임의로 증량하지 마세요.', timesPerDay: 2, days: 7, confidence: 'high' },
    ],
    lowConfidenceCount: 1,
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
