import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react';
import { Camera, Check, Image as ImageIcon, RotateCcw } from 'lucide-react';
import { useNavigate } from 'react-router';
import { createOcrPreviewSession } from '@/entities/document';
import { Button, Card, Header, ImageViewer, RegistrationProgress } from '@/shared/ui';
import { GuidedCamera } from './GuidedCamera';

const GUIDE_ITEMS = ['병원명', '조제일', '약품명·함량', '1회 투약량·횟수·일수'] as const;
const IMAGE_ACCEPT =
  'image/jpeg,image/png,image/heic,image/heif,image/webp,image/bmp,image/tiff,.jpg,.jpeg,.png,.heic,.heif,.webp,.bmp,.tif,.tiff';

function isGif(file: File): boolean {
  return file.type.toLowerCase() === 'image/gif' || file.name.toLowerCase().endsWith('.gif');
}

export function DocumentUploadPage() {
  const navigate = useNavigate();
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewUnavailable, setPreviewUnavailable] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [imageViewerOpen, setImageViewerOpen] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const closeCamera = useCallback(() => setCameraOpen(false), []);

  function openCamera() {
    if (window.isSecureContext && typeof navigator.mediaDevices?.getUserMedia === 'function') {
      setCameraOpen(true);
    } else {
      cameraInputRef.current?.click();
    }
  }

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(file);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  function selectFile(selected: File | null) {
    setSelectionError(null);
    setPreviewUnavailable(false);
    setImageViewerOpen(false);
    if (selected && isGif(selected)) {
      setFile(null);
      setSelectionError('GIF는 지원하지 않아요. 한 장의 사진을 선택해주세요.');
    } else if (selected) {
      setFile(selected);
    }
  }

  function handleSelect(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0] ?? null);
    event.target.value = '';
  }

  function handleUpload() {
    if (!file) return;
    const previewSessionId = createOcrPreviewSession(file);
    navigate('/ocr-review', { replace: true, state: { previewSessionId } });
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-app flex-col bg-background">
      <Header title="약봉투 등록" onBack={() => navigate(-1)} />
      {cameraOpen && <GuidedCamera
        onClose={closeCamera}
        onCapture={(captured) => { selectFile(captured); closeCamera(); }}
        onNativeCamera={() => { closeCamera(); cameraInputRef.current?.click(); }}
        onGallery={() => { closeCamera(); galleryInputRef.current?.click(); }}
      />}
      <input
        ref={cameraInputRef}
        className="sr-only"
        type="file"
        accept={IMAGE_ACCEPT}
        capture="environment"
        onChange={handleSelect}
        aria-label="카메라로 약봉투 촬영"
      />
      <input
        ref={galleryInputRef}
        className="sr-only"
        type="file"
        accept={IMAGE_ACCEPT}
        onChange={handleSelect}
        aria-label="갤러리에서 약봉투 선택"
      />

      <main className="rx-reading-content flex flex-1 flex-col gap-5 px-page-x py-5">
        <RegistrationProgress step={1} />
        <p className="rounded-xl bg-muted-bg px-4 py-3 text-sm leading-relaxed text-muted-foreground">
          촬영한 사진은 확인과 문자 인식을 위해 임시로 사용돼요. 서버에 영구 보관하지 않으며, 서버의 임시 데이터는 보관 시간이 지나면 자동 삭제돼요.
        </p>
        {file && previewUrl ? (
          <>
            <div>
              <h1 className="text-2xl font-bold text-foreground">이 사진으로 등록할까요?</h1>
              <p className="mt-1 text-base text-muted-foreground">
                글자가 잘 보이지 않으면 다시 촬영해 주세요.
              </p>
            </div>
            <div className="relative overflow-hidden rounded-card bg-muted-bg shadow-card">
              {previewUnavailable ? (
                <div className="flex aspect-[4/3] flex-col items-center justify-center gap-2 px-6 text-center">
                  <ImageIcon aria-hidden className="size-10 text-muted-foreground" />
                  <p className="text-sm font-bold text-foreground">미리보기를 표시할 수 없어요</p>
                  <p className="text-sm text-muted-foreground">
                    이 브라우저에서는 미리보기를 지원하지 않아요. 사진은 그대로 등록할 수 있어요.
                  </p>
                </div>
              ) : (
                <button
                  type="button"
                  aria-label="선택한 약봉투 크게 보기"
                  className="block w-full cursor-zoom-in focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                  onClick={() => setImageViewerOpen(true)}
                >
                  <img
                    src={previewUrl}
                    alt="선택한 약봉투 미리보기"
                    className="aspect-[4/3] w-full object-contain"
                    onError={() => setPreviewUnavailable(true)}
                  />
                </button>
              )}
              <button
                type="button"
                className="absolute right-3 bottom-3 flex min-h-touch items-center gap-2 rounded-pill bg-foreground/80 px-4 text-sm font-bold text-card"
                onClick={() => galleryInputRef.current?.click()}
              >
                <RotateCcw aria-hidden className="size-5" />
                다시 선택
              </button>
            </div>
            {!previewUnavailable && (
              <ImageViewer
                open={imageViewerOpen}
                src={previewUrl}
                title="선택한 약봉투 크게 보기"
                onOpenChange={setImageViewerOpen}
              />
            )}
            <p className="text-sm text-muted-foreground">
              {file.name} · {formatFileSize(file.size)}
            </p>
            <div className="mt-auto flex flex-col gap-2 pb-4">
              <Button onClick={handleUpload}>등록하기</Button>
              <Button variant="secondary" onClick={openCamera}>다시 촬영하기</Button>
              <p className="text-center text-sm text-muted-foreground">
                사진을 올린 뒤 바로 읽기 시작해요.
              </p>
            </div>
          </>
        ) : (
          <>
            <div>
              <h1 className="text-2xl font-bold text-foreground">복약안내문을 한 장 담아주세요</h1>
              <p className="mt-1 text-base text-muted-foreground">
                문서의 네 모서리가 잘리지 않고 모두 보이도록, 종이를 평평하게 펴고 바로 위에서 촬영해주세요.
              </p>
            </div>

            <figure className="overflow-hidden rounded-card bg-muted-bg shadow-card">
              <img
                src="/images/medication-capture-guide.png"
                alt="네 테두리가 모두 보이도록 평평하게 놓고 바로 위에서 촬영한 복약안내문 예시"
                width={1024}
                height={1024}
                className="aspect-square w-full object-contain"
              />
              <figcaption className="px-4 pb-4 text-sm text-muted-foreground">
                <span className="mb-1 block font-bold text-foreground">네 모서리 바깥에 여백을 조금 남겨 문서 전체를 담아주세요.</span>
                밝은 곳에서 빛 반사와 그림자를 피하고, 글자에 초점을 맞춰 선명하게 담아주세요.
              </figcaption>
            </figure>

            <Card className="gap-3 p-4" title="이 네 가지가 보이게 담아주세요">
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
              <Button onClick={openCamera}>
                <Camera aria-hidden className="mr-2 size-5" />
                촬영하기
              </Button>
              <Button variant="secondary" onClick={() => galleryInputRef.current?.click()}>
                <ImageIcon aria-hidden className="mr-2 size-5" />
                갤러리에서 선택
              </Button>
              {selectionError && (
                <p role="alert" className="text-center text-sm font-medium text-destructive">
                  {selectionError}
                </p>
              )}
              <p className="text-center text-sm text-disabled-foreground">
                JPG · PNG · HEIC · HEIF · WebP · BMP · TIFF · 한 장
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}
