import { useEffect, useRef, useState } from 'react';
import { Camera, ImageIcon, RotateCw, X } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/shared/ui/dialog';

interface GuidedCameraProps {
  onCapture: (file: File) => void;
  onClose: () => void;
  onNativeCamera: () => void;
  onGallery: () => void;
}

export function GuidedCamera({ onCapture, onClose, onNativeCamera, onGallery }: GuidedCameraProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const guideRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef(false);
  const displayRef = useRef({ fullscreen: false, locked: false });
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState('');
  const [landscapeRequested, setLandscapeRequested] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [rotationHint, setRotationHint] = useState('');

  function releaseDisplay() {
    if (displayRef.current.locked) {
      screen.orientation?.unlock();
      displayRef.current.locked = false;
    }
    if (displayRef.current.fullscreen) {
      displayRef.current.fullscreen = false;
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    }
  }

  async function toggleLandscape() {
    if (rotating) return;
    if (landscapeRequested) {
      releaseDisplay();
      setLandscapeRequested(false);
      setRotationHint('자동 회전으로 돌아왔어요. 휴대폰을 원하는 방향으로 돌려주세요.');
      return;
    }
    setLandscapeRequested(true);
    setRotating(true);
    setRotationHint('휴대폰을 옆으로 돌려 약봉투를 가로로 담아주세요.');
    const orientation = screen.orientation as ScreenOrientation & { lock?: (value: 'landscape') => Promise<void> };
    try {
      if (!orientation?.lock) return;
      if (!document.fullscreenElement) {
        if (!document.documentElement.requestFullscreen) return;
        await document.documentElement.requestFullscreen();
        displayRef.current.fullscreen = true;
      }
      if (!activeRef.current) { releaseDisplay(); return; }
      await orientation.lock('landscape');
      displayRef.current.locked = true;
      if (!activeRef.current) releaseDisplay();
    } catch {
      releaseDisplay();
      if (activeRef.current) setRotationHint('휴대폰의 자동 회전을 켜고 옆으로 돌려주세요. 이 브라우저는 자동 전환을 지원하지 않아요.');
    } finally {
      if (activeRef.current) setRotating(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    let stream: MediaStream | undefined;
    activeRef.current = true;

    async function startCamera() {
      try {
        const opened = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 2560 }, height: { ideal: 1920 } },
        });
        if (cancelled) {
          opened.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = opened;
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = opened;
        await video.play();
      } catch (cause) {
        if (cancelled) return;
        stream?.getTracks().forEach((track) => track.stop());
        const name = cause instanceof Error ? cause.name : '';
        setError(name === 'NotAllowedError'
          ? '카메라 권한을 허용해주세요. 기본 카메라나 저장된 사진으로도 등록할 수 있어요.'
          : name === 'NotFoundError'
            ? '연결된 카메라를 찾지 못했어요. 저장된 사진을 선택해주세요.'
            : '카메라를 열지 못했어요. 다른 앱에서 사용 중인지 확인하거나 기본 카메라를 이용해주세요.');
      }
    }

    void startCamera();
    const closeWhenHidden = () => { if (document.hidden) onClose(); };
    document.addEventListener('visibilitychange', closeWhenHidden);
    return () => {
      cancelled = true;
      activeRef.current = false;
      stream?.getTracks().forEach((track) => track.stop());
      releaseDisplay();
      document.removeEventListener('visibilitychange', closeWhenHidden);
    };
  }, [onClose]);

  function capturePhoto() {
    const video = videoRef.current;
    if (!video || !ready || capturing || !video.videoWidth || !video.videoHeight) return;
    setCapturing(true);
    try {
      const canvas = document.createElement('canvas');
      const frame = video.getBoundingClientRect();
      const guide = guideRef.current?.getBoundingClientRect();
      if (!guide || !frame.width || !frame.height) throw new Error('Capture guide unavailable');
      // object-cover의 확대와 중앙 잘림을 역산해 화면의 가이드 영역을 원본 픽셀로 옮깁니다.
      const scale = Math.max(frame.width / video.videoWidth, frame.height / video.videoHeight);
      const offsetX = (video.videoWidth * scale - frame.width) / 2;
      const offsetY = (video.videoHeight * scale - frame.height) / 2;
      const sourceX = Math.max(0, (guide.left - frame.left + offsetX) / scale);
      const sourceY = Math.max(0, (guide.top - frame.top + offsetY) / scale);
      const sourceWidth = Math.min(video.videoWidth - sourceX, guide.width / scale);
      const sourceHeight = Math.min(video.videoHeight - sourceY, guide.height / scale);
      canvas.width = Math.max(1, Math.round(sourceWidth));
      canvas.height = Math.max(1, Math.round(sourceHeight));
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Canvas unavailable');
      context.drawImage(video, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (!activeRef.current) return;
        if (!blob) {
          setCapturing(false);
          setError('사진을 저장하지 못했어요. 다시 촬영하거나 사진을 선택해주세요.');
          return;
        }
        onCapture(new File([blob], `medication-${Date.now()}.jpg`, { type: 'image/jpeg' }));
      }, 'image/jpeg', 0.95);
    } catch {
      setCapturing(false);
      setError('사진을 저장하지 못했어요. 기본 카메라나 사진 선택을 이용해주세요.');
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        className="inset-0 left-0 top-0 flex h-dvh w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-y-auto rounded-none border-0 bg-slate-950 p-0 text-white"
      >
        <div className="mx-auto flex min-h-full w-full max-w-lg flex-col px-5 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))] landscape:grid landscape:h-full landscape:min-h-0 landscape:max-w-none landscape:grid-cols-[minmax(0,1fr)_180px] landscape:grid-rows-[auto_minmax(0,1fr)] landscape:gap-x-5 landscape:gap-y-2">
          <header className="relative flex min-h-12 shrink-0 items-center justify-center landscape:col-span-2">
            <DialogTitle className="text-xl text-white">약봉투 촬영</DialogTitle>
            <button type="button" aria-label="카메라 닫기" onClick={onClose} className="absolute right-0 flex size-12 items-center justify-center rounded-full bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">
              <X aria-hidden className="size-6" />
            </button>
          </header>
          <DialogDescription className="mt-2 text-center text-sm text-slate-300 landscape:sr-only">
            가이드 안쪽만 촬영돼요. 약봉투의 네 모서리를 안에 맞춰주세요
          </DialogDescription>

          <div className="relative my-5 min-h-[min(48dvh,360px)] flex-1 overflow-hidden rounded-2xl bg-black landscape:col-start-1 landscape:row-start-2 landscape:my-0 landscape:min-h-0 landscape:h-full" style={{ containerType: 'size' }}>
            <video ref={videoRef} autoPlay muted playsInline aria-label="실시간 카메라"
              onPlaying={() => setReady(true)} className="absolute inset-0 h-full w-full object-cover" />
            <div ref={guideRef} data-testid="camera-capture-guide" aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 aspect-[3/2] w-[86%] max-w-[60dvh] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-white/30 shadow-[0_0_0_100vmax_rgba(0,0,0,0.48)] landscape:max-w-[135cqh]">
              <span className="absolute -left-0.5 -top-0.5 size-8 rounded-tl-lg border-l-4 border-t-4 border-white" />
              <span className="absolute -right-0.5 -top-0.5 size-8 rounded-tr-lg border-r-4 border-t-4 border-white" />
              <span className="absolute -bottom-0.5 -left-0.5 size-8 rounded-bl-lg border-b-4 border-l-4 border-white" />
              <span className="absolute -bottom-0.5 -right-0.5 size-8 rounded-br-lg border-b-4 border-r-4 border-white" />
            </div>
            {!ready && !error && <p role="status" className="absolute inset-0 grid place-items-center px-8 text-center text-sm">카메라를 연결하고 있어요…</p>}
            {error && <div role="alert" className="absolute inset-0 flex items-center justify-center bg-slate-950/95 p-8 text-center text-base leading-relaxed">{error}</div>}
          </div>

          <div className="shrink-0 landscape:col-start-2 landscape:row-start-2 landscape:min-h-0 landscape:overflow-y-auto">
          <button type="button" onClick={() => void toggleLandscape()} disabled={rotating} aria-pressed={landscapeRequested}
            className="mb-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-white/10 px-3 text-sm font-medium disabled:opacity-50 focus-visible:outline focus-visible:outline-white">
            <RotateCw aria-hidden className="size-4" />{landscapeRequested ? '자동 회전으로 돌아가기' : '가로 촬영으로 전환'}
          </button>
          {rotationHint && <p role="status" className="mb-3 text-center text-sm leading-relaxed text-teal-200">{rotationHint}</p>}
          <p className="shrink-0 text-center text-sm leading-relaxed text-slate-300 landscape:hidden">밝은 곳에서 종이를 평평하게 펴고<br />글자에 초점을 맞춘 뒤 촬영해주세요.</p>
          <div className="my-4 flex shrink-0 justify-center">
            <button type="button" aria-label="사진 촬영" disabled={!ready || capturing || Boolean(error)} onClick={capturePhoto}
              className="flex size-20 items-center justify-center rounded-full border-4 border-white p-1.5 focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-white disabled:opacity-40">
              <span className="flex size-full items-center justify-center rounded-full bg-primary"><Camera aria-hidden className="size-7 text-white" /></span>
            </button>
          </div>
          <div className="flex shrink-0 justify-center gap-3 landscape:flex-col landscape:gap-2">
            <button type="button" onClick={onNativeCamera} className="min-h-12 rounded-xl bg-white/10 px-3 text-sm font-medium focus-visible:outline focus-visible:outline-white">기본 카메라로 촬영</button>
            <button type="button" onClick={onGallery} className="flex min-h-12 items-center gap-2 rounded-xl bg-white/10 px-3 text-sm font-medium focus-visible:outline focus-visible:outline-white"><ImageIcon aria-hidden className="size-4" />사진에서 선택</button>
          </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
