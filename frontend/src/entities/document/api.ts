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
import { mockCancelOcrResult, mockConfirmOcrResult, mockOcrResult, mockUploadDocument } from './api.mock';
import type {
  ConfirmOcrResultPayload,
  ConfirmOcrResultResponse,
  OcrResult,
  UploadDocumentsResult,
} from './types';

const idempotencyKeys = new WeakMap<File, string>();
const pendingUploads = new WeakMap<File, Promise<UploadDocumentsResult>>();

export type OcrPreviewSessionId = string;

export interface OcrPreviewImages {
  originalImageUrl: string;
  processedImageUrl: string;
}

interface OcrPreviewSession {
  file: File;
  images?: OcrPreviewImages;
  imageRequest?: Promise<OcrPreviewImages | null>;
  released: boolean;
}

/**
 * OCR 검토 중에만 원본 File·blob URL을 탭 메모리에 보관합니다.
 * sessionStorage·history state에는 ID만 지나가며, 새로고침하면 이 Map은 비워집니다.
 */
const ocrPreviewSessions = new Map<OcrPreviewSessionId, OcrPreviewSession>();

function createOcrPreviewSessionId(): OcrPreviewSessionId {
  const random = crypto.getRandomValues(new Uint8Array(16));
  return `ocr-preview-${Array.from(random, (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
}

function revokePreviewImages(images: OcrPreviewImages): void {
  URL.revokeObjectURL(images.originalImageUrl);
  URL.revokeObjectURL(images.processedImageUrl);
}

/** 선택한 사진을 history에 넣지 않고 현재 브라우저 탭의 OCR 검토 세션으로 시작합니다. */
export function createOcrPreviewSession(file: File): OcrPreviewSessionId {
  const sessionId = createOcrPreviewSessionId();
  ocrPreviewSessions.set(sessionId, { file, released: false });
  return sessionId;
}

/** 업로드 효과가 원본 File을 읽는 유일한 경로입니다. 세션이 사라진 새로고침에서는 null입니다. */
export function getOcrPreviewSessionFile(sessionId: OcrPreviewSessionId | null | undefined): File | null {
  return sessionId ? ocrPreviewSessions.get(sessionId)?.file ?? null : null;
}

/**
 * 원본은 선택 File에서 즉시 만들고 전처리본만 인증 fetch 합니다.
 * 둘 다 준비되기 전에는 세션에 URL을 저장하지 않아 서버 사진 삭제 확인을 보낼 수 없습니다.
 */
export function loadOcrPreviewImages(
  sessionId: OcrPreviewSessionId,
  ocrJobId: string,
  mockProcessedImageUrl: string,
): Promise<OcrPreviewImages | null> {
  const session = ocrPreviewSessions.get(sessionId);
  if (!session || session.released) return Promise.resolve(null);
  if (session.images) return Promise.resolve(session.images);
  if (session.imageRequest) return session.imageRequest;

  let originalImageUrl: string;
  try {
    originalImageUrl = URL.createObjectURL(session.file);
  } catch (error) {
    return Promise.reject(error);
  }
  const request = getOcrProcessedImageUrl(ocrJobId, mockProcessedImageUrl)
    .then((processedImageUrl) => {
      const images = { originalImageUrl, processedImageUrl };
      if (session.released || ocrPreviewSessions.get(sessionId) !== session) {
        revokePreviewImages(images);
        return null;
      }
      session.images = images;
      return images;
    })
    .catch((error: unknown) => {
      URL.revokeObjectURL(originalImageUrl);
      throw error;
    })
    .finally(() => {
      session.imageRequest = undefined;
    });
  session.imageRequest = request;
  return request;
}

/** 검토 종료와 unmount 때 blob URL·File 참조를 즉시 끊습니다. */
export function releaseOcrPreviewSession(sessionId: OcrPreviewSessionId | null | undefined): void {
  if (!sessionId) return;
  const session = ocrPreviewSessions.get(sessionId);
  if (!session) return;
  session.released = true;
  ocrPreviewSessions.delete(sessionId);
  if (session.images) revokePreviewImages(session.images);
}

function idempotencyKeyFor(file: File): string {
  const existing = idempotencyKeys.get(file);
  if (existing) return existing;
  // 휴대폰의 HTTP LAN 접속에서는 randomUUID가 없지만 getRandomValues는 지원됩니다.
  const random = crypto.getRandomValues(new Uint8Array(16));
  const key = `ocr-${Array.from(random, (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
  idempotencyKeys.set(file, key);
  return key;
}

/** OCR에 사용한 원근·조명 보정 이미지를 인증 fetch로 불러옵니다. */
export function getOcrProcessedImageUrl(ocrJobId: string, mockImageUrl: string): Promise<string> {
  return USE_MOCK
    ? Promise.resolve(mockImageUrl)
    : http
      .getBlob(`/v1/ocr/jobs/${encodeURIComponent(ocrJobId)}/processed-image`)
      .then((blob) => URL.createObjectURL(blob));
}

/**
 * 브라우저가 원본 File과 전처리본을 모두 확보한 뒤 서버 사진만 지웁니다.
 * 삭제 실패는 등록 저장을 되돌리지 않으며, 짧게 한 번만 재시도합니다.
 */
export async function releaseOcrJobImages(ocrJobId: string): Promise<void> {
  if (USE_MOCK) return;
  let lastError: unknown;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await http.post<void>(`/v1/ocr/jobs/${encodeURIComponent(ocrJobId)}/release-images`);
      return;
    } catch (error: unknown) {
      lastError = error;
    }
  }
  throw lastError;
}

/** 조제약 OCR 작업 생성 — POST /ocr */
export function uploadDocument(file: File): Promise<UploadDocumentsResult> {
  const existing = pendingUploads.get(file);
  if (existing) return existing;

  // StrictMode effect 재실행도 같은 요청을 공유하되, 완료 후에는 재시도를 허용합니다.
  const request = requestUploadDocument(file).finally(() => {
    pendingUploads.delete(file);
  });
  pendingUploads.set(file, request);
  return request;
}

async function requestUploadDocument(file: File): Promise<UploadDocumentsResult> {
  if (USE_MOCK) {
    await mockDelay();
    return mockUploadDocument(file);
  }

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

/** 재촬영 전 검토 대기 작업 취소 — POST /ocr/jobs/{ocrJobId}/cancel */
export async function cancelOcrResult(batchId: string): Promise<void> {
  if (USE_MOCK) {
    await mockDelay();
    mockCancelOcrResult(batchId);
  } else {
    await http.post<void>(`/v1/ocr/jobs/${encodeURIComponent(batchId)}/cancel`);
  }
}

/** 사용자 수정본 확정 — PATCH /ocr/jobs/{ocrJobId} */
export async function confirmOcrResult(
  batchId: string,
  payload: ConfirmOcrResultPayload,
  options: { registrationEdit?: boolean } = {},
): Promise<ConfirmOcrResultResponse> {
  if (USE_MOCK) {
    await mockDelay();
    return mockConfirmOcrResult(payload);
  }
  const query = options.registrationEdit ? '?registrationEdit=true' : '';
  const confirmed = await http.patch<ConfirmOcrResultResponse>(
    `/v1/ocr/jobs/${encodeURIComponent(batchId)}${query}`,
    payload,
  );
  return confirmed;
}
