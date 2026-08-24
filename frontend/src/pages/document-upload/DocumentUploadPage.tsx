import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { Camera, Check, Image as ImageIcon, RotateCcw } from 'lucide-react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { uploadDocument } from '@/entities/document';
import { Button, Card, ErrorDialog, Header } from '@/shared/ui';

const GUIDE_ITEMS = ['조제일', '약 이름과 용량', '하루 몇 번, 며칠분'] as const;

export function DocumentUploadPage() {
  const navigate = useNavigate();
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(file);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  function handleSelect(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    if (selected) setFile(selected);
    event.target.value = '';
  }

  async function handleUpload() {
    if (!file || uploading) return;
    setUploading(true);
    setUploadError(null);
    try {
      const { batchId } = await uploadDocument(file, 'initial');
      toast.success('약봉투를 등록했어요.');
      navigate('/ocr-review', { state: { batchId } });
    } catch (error: unknown) {
      setUploadError(error instanceof Error ? error.message : '약봉투를 등록하지 못했어요.');
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="약봉투 등록" onBack={() => navigate(-1)} />
      <input
        ref={cameraInputRef}
        className="sr-only"
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleSelect}
        aria-label="카메라로 약봉투 촬영"
      />
      <input
        ref={galleryInputRef}
        className="sr-only"
        type="file"
        accept="image/*"
        onChange={handleSelect}
        aria-label="갤러리에서 약봉투 선택"
      />

      <main className="flex flex-1 flex-col gap-5 px-page-x py-5">
        {file && previewUrl ? (
          <>
            <div>
              <h1 className="text-2xl font-bold text-foreground">이 사진으로 등록할까요?</h1>
              <p className="mt-1 text-base text-muted-foreground">
                글자가 흐리면 다시 담는 게 빠릅니다.
              </p>
            </div>
            <div className="relative overflow-hidden rounded-card bg-muted-bg shadow-card">
              <img
                src={previewUrl}
                alt="선택한 약봉투 미리보기"
                className="aspect-[4/5] w-full object-contain"
              />
              <button
                type="button"
                className="absolute right-3 bottom-3 flex min-h-touch items-center gap-2 rounded-pill bg-foreground/80 px-4 text-sm font-bold text-card"
                onClick={() => galleryInputRef.current?.click()}
              >
                <RotateCcw aria-hidden className="size-5" />
                다시 선택
              </button>
            </div>
            <p className="text-sm text-muted-foreground">
              {file.name} · {formatFileSize(file.size)}
            </p>
            <div className="mt-auto flex flex-col gap-2 pb-4">
              <Button onClick={handleUpload} disabled={uploading}>
                {uploading ? '읽는 중...' : '등록하기'}
              </Button>
              <p className="text-center text-sm text-muted-foreground">읽는 데 10초쯤 걸립니다.</p>
            </div>
          </>
        ) : (
          <>
            <div>
              <h1 className="text-2xl font-bold text-foreground">약봉투를 한 장 담아주세요</h1>
              <p className="mt-1 text-base text-muted-foreground">약국에서 받은 봉투 앞면이면 됩니다.</p>
            </div>

            <div className="flex aspect-square items-center justify-center rounded-card bg-muted-bg p-8 text-primary shadow-card">
              <svg aria-hidden viewBox="0 0 240 240" className="size-full" fill="none" stroke="currentColor" strokeWidth="3">
                <path d="M20 60V34a14 14 0 0 1 14-14h26M180 20h26a14 14 0 0 1 14 14v26M220 180v26a14 14 0 0 1-14 14h-26M60 220H34a14 14 0 0 1-14-14v-26" />
                <path d="M78 87h84v105H78zM78 87l42-26 42 26" className="text-border" />
                <path d="M96 126h48M96 148h48M96 170h28" className="text-border" />
              </svg>
            </div>

            <Card className="gap-3 p-4" title="이 세 가지가 보이게 담아주세요">
              <ul className="flex flex-col gap-2">
                {GUIDE_ITEMS.map((item) => (
                  <li key={item} className="flex items-center gap-3 text-base text-foreground">
                    <Check aria-hidden className="size-5 shrink-0 text-primary" />
                    {item}
                  </li>
                ))}
              </ul>
            </Card>

            <div className="mt-auto flex flex-col gap-2 pb-4">
              <Button onClick={() => cameraInputRef.current?.click()}>
                <Camera aria-hidden className="mr-2 size-5" />
                촬영하기
              </Button>
              <Button variant="secondary" onClick={() => galleryInputRef.current?.click()}>
                <ImageIcon aria-hidden className="mr-2 size-5" />
                갤러리에서 선택
              </Button>
              <p className="text-center text-sm text-disabled-foreground">JPG · PNG · 한 장</p>
            </div>
          </>
        )}
      </main>

      <ErrorDialog
        open={uploadError !== null}
        title="약봉투를 등록하지 못했어요"
        message={uploadError ?? ''}
        onRetry={() => {
          setUploadError(null);
          void handleUpload();
        }}
        secondaryLabel="다시 선택"
        onSecondary={() => {
          setUploadError(null);
          galleryInputRef.current?.click();
        }}
      />
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}
