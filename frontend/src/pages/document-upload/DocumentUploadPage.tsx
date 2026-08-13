import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { Button, Card, Header } from '@/shared/ui';
import type { CapturedDocument } from '@/entities/document';

/**
 * REQ-DOC-001 · Figma `05 문서 업로드` (66:97)
 *
 * 실제 카메라·파일 접근이 없는 개발 환경이라, "카메라로 촬영"·"갤러리·파일 선택"은
 * docs/sample-docs의 환자1(김철수) 문서 3종을 순서대로 담는 것으로 흉내냅니다.
 * 카메라는 한 장씩, 갤러리는 남은 문서를 한 번에 담아 D07(등록할 문서 확인)로 이동합니다.
 * D07에서 "문서 추가"를 누르면 지금까지 담은 목록을 들고 이 화면으로 돌아옵니다.
 */
const SAMPLE_FILE_POOL: Array<{ fileName: string; sizeLabel: string }> = [
  { fileName: '퇴원기록지_01.jpg', sizeLabel: '2.1MB' },
  { fileName: '조제약봉투_01.jpg', sizeLabel: '1.6MB' },
  { fileName: '복약지도서_01.jpg', sizeLabel: '1.8MB' },
];

interface UploadLocationState {
  captured?: CapturedDocument[];
}

export function DocumentUploadPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as UploadLocationState | null) ?? {};
  const [captured] = useState<CapturedDocument[]>(state.captured ?? []);

  function goToConfirm(next: CapturedDocument[]) {
    navigate('/dev/document-confirm', { state: { captured: next } });
  }

  function handleCameraCapture() {
    const sample = SAMPLE_FILE_POOL[captured.length % SAMPLE_FILE_POOL.length];
    const doc: CapturedDocument = {
      id: `cap-${captured.length}-${captured.length + 1}`,
      fileName: sample.fileName,
    };
    goToConfirm([...captured, doc]);
  }

  function handleGalleryPick() {
    // 갤러리·파일 선택은 다중 선택을 지원하므로 남은 샘플 문서를 한 번에 담습니다.
    const remaining = SAMPLE_FILE_POOL.slice(captured.length);
    const picked = (remaining.length > 0 ? remaining : SAMPLE_FILE_POOL).map((f, i) => ({
      id: `gal-${captured.length}-${i}`,
      fileName: f.fileName,
      sizeLabel: f.sizeLabel,
    }));
    goToConfirm([...captured, ...picked]);
  }

  const latest = captured[captured.length - 1];

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="문서 업로드" onBack={() => navigate(-1)} />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        <p className="text-base text-foreground">
          퇴원요약지, 처방전, 진료안내문을 등록해주세요.
        </p>

        <Card title="지원 형식">JPG · PNG · PDF · 여러 장 선택 가능</Card>

        <Card title="선명하게 촬영해주세요">
          문서 전체가 보이도록 밝은 곳에서 정면으로 촬영하세요.
        </Card>

        {latest && (
          <Card title="선택된 문서">
            {latest.fileName}
            {latest.sizeLabel ? ` · ${latest.sizeLabel}` : ''}
          </Card>
        )}

        <div className="flex-1" />

        <div className="flex flex-col gap-2 pb-4">
          <Button onClick={handleCameraCapture}>카메라로 촬영</Button>
          <Button variant="secondary" onClick={handleGalleryPick}>
            갤러리 · 파일 선택
          </Button>
        </div>
      </main>
    </div>
  );
}
