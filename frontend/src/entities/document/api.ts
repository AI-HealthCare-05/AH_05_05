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
} from './types';

const idempotencyKeys = new WeakMap<File, string>();
const documentImageUrls = new Map<string, Promise<string>>();

type OcrImageKind = 'original' | 'processed';

function imageCacheKey(ocrJobId: string, kind: OcrImageKind): string {
  return `${ocrJobId}:${kind}`;
}

function revokeAuthenticatedImageUrl(ocrJobId: string): void {
  for (const kind of ['original', 'processed'] as const) {
    const key = imageCacheKey(ocrJobId, kind);
    const pendingUrl = documentImageUrls.get(key);
    if (!pendingUrl) continue;
    documentImageUrls.delete(key);
    void pendingUrl.then((url) => URL.revokeObjectURL(url), () => undefined);
  }
}

function revokeAllAuthenticatedImageUrls(): void {
  for (const pendingUrl of documentImageUrls.values()) {
    void pendingUrl.then((url) => URL.revokeObjectURL(url), () => undefined);
  }
  documentImageUrls.clear();
}

function idempotencyKeyFor(file: File): string {
  const existing = idempotencyKeys.get(file);
  if (existing) return existing;
  const key = `ocr-${crypto.randomUUID()}`;
  idempotencyKeys.set(file, key);
  return key;
}

function authenticatedImageUrl(ocrJobId: string, kind: OcrImageKind): Promise<string> {
  const key = imageCacheKey(ocrJobId, kind);
  const existing = documentImageUrls.get(key);
  if (existing) return existing;
  const suffix = kind === 'processed' ? '/processed-image' : '/image';
  const request = http
    .getBlob(`/v1/ocr/jobs/${encodeURIComponent(ocrJobId)}${suffix}`)
    .then((blob) => URL.createObjectURL(blob))
    .catch((error: unknown) => {
      documentImageUrls.delete(key);
      throw error;
    });
  documentImageUrls.set(key, request);
  return request;
}

/**
 * 원본 이미지는 <img> 태그에 Bearer 헤더를 붙일 수 없어서 별도로 인증 fetch 합니다.
 * OCR JSON 조회와 분리해, 미리보기만 실패해도 검토·저장을 계속할 수 있게 합니다.
 */
export function getOcrDocumentImageUrl(ocrJobId: string, mockImageUrl: string): Promise<string> {
  return USE_MOCK ? Promise.resolve(mockImageUrl) : authenticatedImageUrl(ocrJobId, 'original');
}

/** OCR에 사용한 원근·조명 보정 이미지를 인증 fetch로 불러옵니다. */
export function getOcrProcessedImageUrl(ocrJobId: string, mockImageUrl: string): Promise<string> {
  return USE_MOCK ? Promise.resolve(mockImageUrl) : authenticatedImageUrl(ocrJobId, 'processed');
}

/** 검토 화면이 떠나거나 저장을 마치면 인증 이미지 blob URL을 해제합니다. */
export function releaseOcrDocumentImageUrl(ocrJobId: string): void {
  revokeAuthenticatedImageUrl(ocrJobId);
}

/** 조제약 OCR 작업 생성 — POST /ocr */
export async function uploadDocument(file: File): Promise<UploadDocumentsResult> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUploadDocument(file);
  }

  revokeAllAuthenticatedImageUrls();

  const form = new FormData();
  form.append('file', file);
  const uploaded = await http.post<UploadDocumentsResult>('/v1/ocr', form, {
    'Idempotency-Key': idempotencyKeyFor(file),
  });
  return uploaded;
}

/** 조제약 OCR 상태·결과 조회 — GET /ocr/jobs/{ocrJobId} */
export async function getOcrResult(batchId: string): Promise<OcrResult> {
  if (USE_MOCK) {
    await mockDelay();
    return mockOcrResult(batchId);
  }
  return http.get<OcrResult>(`/v1/ocr/jobs/${encodeURIComponent(batchId)}`);
}

/** 사용자 수정본 확정 — PATCH /ocr/jobs/{ocrJobId} */
export async function confirmOcrResult(
  batchId: string,
  payload: ConfirmOcrResultPayload,
): Promise<ConfirmOcrResultResponse> {
  if (USE_MOCK) {
    await mockDelay();
    return mockConfirmOcrResult(payload);
  }
  const confirmed = await http.patch<ConfirmOcrResultResponse>(
    `/v1/ocr/jobs/${encodeURIComponent(batchId)}`,
    payload,
  );
  releaseOcrDocumentImageUrl(batchId);
  return confirmed;
}
