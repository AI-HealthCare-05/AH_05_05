import { useLocation, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { Button, Card, Header } from '@/shared/ui';
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

  function handleAddMore() {
    navigate('/dev/document-upload', { state: { captured } });
  }

  async function handleFinish() {
    const { batchId } = await uploadDocuments(captured, 'initial');
    toast.success('업로드 완료');
    navigate('/dev/ocr-review', { state: { batchId } });
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="문서 업로드" onBack={() => navigate(-1)} />

      <main className="flex flex-1 flex-col gap-3 px-page-x py-4">
        <p className="text-base text-foreground">
          등록할 문서를 확인하고 문서를 추가하거나 완료해주세요.
        </p>

        <Card tone="info" title={`등록할 문서 · ${captured.length}장`}>
          <div className="flex flex-wrap gap-3 py-1">
            {captured.map((doc, i) => (
              <div
                key={doc.id}
                className="flex h-[88px] w-[96px] shrink-0 items-center justify-center rounded-input border border-border bg-card text-sm font-bold text-foreground"
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
          <Button variant="secondary" onClick={handleAddMore}>
            문서 추가
          </Button>
          <Button onClick={handleFinish}>등록 완료</Button>
        </div>
      </main>
    </div>
  );
}
