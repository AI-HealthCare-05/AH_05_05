import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button, Card, ErrorDialog, Header } from '@/shared/ui';
import { uploadDocuments, type CapturedDocument } from '@/entities/document';

/**
 * REQ-DOC-001 상태 변형 · Figma `D07 등록할 문서 확인` (201:25)
 *
 * 05에서 카메라/갤러리로 담아온 문서를 확인합니다.
 * "문서 추가"는 지금까지 담은 목록을 들고 05로 돌아가 촬영 루프를 이어갑니다
 * (요구사항 "한 장 촬영 후 문서 추가/등록 완료 선택하는 루프").
 * 독립적으로 /dev/document-confirm 을 바로 열었을 때를 위해 기본 목업 2장을 준비해뒀습니다.
 */
interface ConfirmLocationState {
  captured?: CapturedDocument[];
}

const DEFAULT_CAPTURED: CapturedDocument[] = [
  { id: 'sample-1', fileName: '퇴원기록지_01.jpg' },
  { id: 'sample-2', fileName: '조제약봉투_01.jpg' },
];

export function DocumentConfirmPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state as ConfirmLocationState | null) ?? {};
  const captured =
    state.captured && state.captured.length > 0 ? state.captured : DEFAULT_CAPTURED;

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  function handleAddMore() {
    navigate('/dev/document-upload', { state: { captured } });
  }

  /**
   * 업로드는 사용자가 버튼을 눌러 시작한 작업이고 뒤에 화면이 남아 있으므로 실패를
   * 팝업으로 알립니다. catch 가 없으면 413(용량)·415(형식)·500 에서 버튼을 눌렀는데
   * 화면이 그대로라, 사용자는 자기가 잘못 눌렀다고 생각하고 계속 누릅니다.
   */
  async function handleFinish() {
    if (uploading) return;
    setUploading(true);
    setUploadError(null);
    try {
      const { batchId } = await uploadDocuments(captured, 'initial');
      toast.success('업로드 완료');
      navigate('/dev/ocr-review', { state: { batchId } });
    } catch (error: unknown) {
      setUploadError(
        error instanceof Error ? error.message : '문서를 등록하지 못했어요.',
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="문서 업로드" onBack={() => navigate(-1)} />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        <p className="text-base text-foreground">
          등록할 문서를 확인하고 문서를 추가하거나 완료해주세요.
        </p>

        <Card tone="info" title={`등록할 문서 · ${captured.length}장`}>
          {/*
            등록하는 문서는 퇴원요약지·처방전이라 A4 세로입니다. 고정폭 + flex-wrap 대신
            grid 를 쓰면 375px 에서 장수가 늘어도 열이 흔들리지 않습니다.
          */}
          <div className="grid grid-cols-3 gap-3 py-1">
            {captured.map((doc, i) => (
              <div
                key={doc.id}
                className="flex aspect-[3/4] items-center justify-center rounded-input border border-border bg-card text-sm font-bold text-foreground"
              >
                {i + 1}쪽
              </div>
            ))}
          </div>
          <span className="block text-sm text-muted-foreground">
            {captured.map((d) => d.fileName).join(' · ')}
          </span>
        </Card>

        <div className="flex-1" />

        <div className="flex flex-col gap-2 pb-4">
          <Button variant="secondary" onClick={handleAddMore} disabled={uploading}>
            문서 추가
          </Button>
          {/* 전송 중 중복 전송을 막습니다. */}
          <Button onClick={handleFinish} disabled={uploading}>
            {uploading ? '등록 중...' : '등록 완료'}
          </Button>
        </div>
      </main>

      <ErrorDialog
        open={uploadError !== null}
        title="문서를 등록하지 못했어요"
        message={uploadError ?? ''}
        onRetry={() => {
          setUploadError(null);
          void handleFinish();
        }}
        secondaryLabel="문서 다시 선택"
        onSecondary={() => {
          setUploadError(null);
          navigate('/dev/document-upload', { state: { captured } });
        }}
      />
    </div>
  );
}
