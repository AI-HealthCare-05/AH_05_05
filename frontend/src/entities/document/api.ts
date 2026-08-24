/**
 * 문서·OCR API. 화면은 이 함수들만 부릅니다.
 *
 * 각 함수는 `USE_MOCK` 이면 api.mock.ts 를, 아니면 실제 엔드포인트를 호출합니다.
 * 백엔드가 엔드포인트를 하나 완성하면 그 함수의 mock 분기만 지우면 되고,
 * 화면 코드는 건드리지 않습니다.
 *
 * 엔드포인트 진행 상황은 GitHub 이슈에서 관리합니다.
 */
import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockConfirmOcrResult, mockOcrResult, mockUploadDocument } from './api.mock';
import type {
  ConfirmOcrResultPayload,
  ConfirmOcrResultResponse,
  OcrResult,
  UploadDocumentsResult,
  UploadPurpose,
} from './types';

/** REQ-DOC-001 — POST /documents (multipart/form-data) · 명세 3-1 */
export async function uploadDocument(file: File, purpose: UploadPurpose): Promise<UploadDocumentsResult> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUploadDocument();
  }

  const form = new FormData();
  form.append('purpose', purpose);
  form.append('file', file);
  return http.post<UploadDocumentsResult>('/documents', form);
}

/** REQ-DOC-003 — GET /documents/{batchId}/ocr · 명세 3-2 */
export async function getOcrResult(batchId: string): Promise<OcrResult> {
  if (USE_MOCK) {
    await mockDelay();
    return mockOcrResult(batchId);
  }
  return http.get<OcrResult>(`/documents/${encodeURIComponent(batchId)}/ocr`);
}

/** REQ-DOC-003 — PATCH /documents/{batchId}/ocr · 명세 3-3 */
export async function confirmOcrResult(
  batchId: string,
  payload: ConfirmOcrResultPayload,
): Promise<ConfirmOcrResultResponse> {
  if (USE_MOCK) {
    await mockDelay();
    return mockConfirmOcrResult(payload);
  }
  return http.patch<ConfirmOcrResultResponse>(
    `/documents/${encodeURIComponent(batchId)}/ocr`,
    payload,
  );
}
