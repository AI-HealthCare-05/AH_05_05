import { useEffect, useRef, useState } from 'react';
import { Camera, ImageIcon, RotateCw, X } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/shared/ui/dialog';

interface GuidedCameraProps {
  onCapture: (file: File) => void;
  onClose: () => void;
  onNativeCamera: () => void;
  onGallery: () => void;
}

type ZoomRange = { min: number; max: number; step: number; value: number };
type CameraCapabilities = MediaTrackCapabilities & { zoom?: { min: number; max: number; step?: number } };
type CameraSettings = MediaTrackSettings & { zoom?: number };
type StillCamera = {
  takePhoto: (settings?: { imageWidth: number; imageHeight: number }) => Promise<Blob>;
  getPhotoCapabilities?: () => Promise<{ imageWidth: { max: number }; imageHeight: { max: number } }>;
};
type StillCameraConstructor = new (track: MediaStreamTrack) => StillCamera;

export function GuidedCamera({ onCapture, onClose, onNativeCamera, onGallery }: GuidedCameraProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const trackRef = useRef<MediaStreamTrack | null>(null);
  const capturePendingRef = useRef(false);
  const activeRef = useRef(false);
  const displayRef = useRef({ fullscreen: false, locked: false });
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState('');
  const [landscapeRequested, setLandscapeRequested] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [rotationHint, setRotationHint] = useState('');
  const [zoom, setZoom] = useState<ZoomRange | null>(null);
  const [zooming, setZooming] = useState(false);
  const [zoomHint, setZoomHint] = useState('');
  const [videoAspect, setVideoAspect] = useState(4 / 3);

  async function changeZoom(value: number) {
    const track = trackRef.current;
    if (!track || !zoom || zooming || capturing) return;
    const next = Math.min(zoom.max, Math.max(zoom.min, zoom.min + Math.round((value - zoom.min) / zoom.step) * zoom.step));
    setZooming(true);
    try {
      await track.applyConstraints({ advanced: [{ zoom: next } as MediaTrackConstraintSet] });
      if (!activeRef.current) return;
      const actual = (track.getSettings() as CameraSettings).zoom ?? next;
      setZoom({ ...zoom, value: actual });
      setZoomHint('');
    } catch {
      if (activeRef.current) setZoomHint('배율을 바꾸지 못했어요. 기본 카메라에서 조절해주세요.');
    } finally {
      if (activeRef.current) setZooming(false);
    }
  }

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
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 4096 }, height: { ideal: 3072 } },
        });
        if (cancelled) {
          opened.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = opened;
        const track = opened.getVideoTracks()[0];
        trackRef.current = track ?? null;
        try {
          const range = (track?.getCapabilities?.() as CameraCapabilities | undefined)?.zoom;
          if (range && Number.isFinite(range.min) && Number.isFinite(range.max) && range.min > 0 && range.max > range.min) {
            setZoom({
              min: range.min, max: range.max, step: range.step && range.step > 0 ? range.step : 0.1,
              value: (track.getSettings() as CameraSettings).zoom ?? range.min,
            });
          }
        } catch { /* Camera controls are optional; the live stream remains usable. */ }
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
      trackRef.current = null;
      stream?.getTracks().forEach((track) => track.stop());
      releaseDisplay();
      document.removeEventListener('visibilitychange', closeWhenHidden);
    };
  }, [onClose]);

  async function capturePhoto() {
    const video = videoRef.current;
    if (!video || !ready || capturePendingRef.current || zooming || !video.videoWidth || !video.videoHeight) return;
    capturePendingRef.current = true;
    setCapturing(true);
    try {
      // Prefer a still exposure: unlike a preview frame, this can use the sensor's photo resolution.
      const Capture = (window as Window & { ImageCapture?: StillCameraConstructor }).ImageCapture;
      const track = trackRef.current;
      if (Capture && track) {
        try {
          const camera = new Capture(track);
          let settings: { imageWidth: number; imageHeight: number } | undefined;
          try {
            const capabilities = await camera.getPhotoCapabilities?.();
            const width = capabilities?.imageWidth.max ?? 0;
            const height = capabilities?.imageHeight.max ?? 0;
            if (width > 0 && height > 0) {
              const scale = Math.min(1, 10000 / Math.max(width, height), Math.sqrt(40_000_000 / (width * height)));
              settings = { imageWidth: Math.floor(width * scale), imageHeight: Math.floor(height * scale) };
            }
          } catch { /* Default photo settings are still usable. */ }
          if (!activeRef.current) return;
          const photo = await camera.takePhoto(settings);
          if (!activeRef.current) return;
          if (photo.size && (photo.type === 'image/jpeg' || photo.type === 'image/png')) {
            onCapture(new File([photo], `medication-${Date.now()}.${photo.type === 'image/png' ? 'png' : 'jpg'}`, { type: photo.type }));
            return;
          }
        } catch { /* Fall back to the complete native video frame when still capture is unavailable. */ }
      }
      if (!activeRef.current) return;
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Canvas unavailable');
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.98));
      if (!activeRef.current) return;
      if (!blob) throw new Error('Photo encoding failed');
      onCapture(new File([blob], `medication-${Date.now()}.jpg`, { type: 'image/jpeg' }));
    } catch {
      if (activeRef.current) setError('사진을 저장하지 못했어요. 기본 카메라나 사진 선택을 이용해주세요.');
    } finally {
      capturePendingRef.current = false;
      if (activeRef.current) setCapturing(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        style={{ backgroundImage: 'none', boxShadow: 'none' }}
        className="inset-0 left-0 top-0 flex h-dvh w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-y-auto rounded-none border-0 bg-slate-950 p-0 text-white"
      >
        <div className="mx-auto flex h-full min-h-0 w-full max-w-lg flex-col px-5 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))] landscape:grid landscape:h-full landscape:min-h-0 landscape:max-w-none landscape:grid-cols-[minmax(0,1fr)_180px] landscape:grid-rows-[auto_minmax(0,1fr)] landscape:gap-x-5 landscape:gap-y-2">
          <header className="relative flex min-h-12 shrink-0 items-center justify-center landscape:col-span-2">
            <DialogTitle className="text-xl text-white">약봉투 촬영</DialogTitle>
            <button type="button" aria-label="카메라 닫기" onClick={onClose} className="absolute right-0 flex size-12 items-center justify-center rounded-full bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white">
              <X aria-hidden className="size-6" />
            </button>
          </header>
          <DialogDescription className="mt-2 text-center text-sm text-slate-300 landscape:sr-only">
            약봉투의 네 모서리를 화면에 담아주세요. 사진 전체가 저장돼요.
          </DialogDescription>

          <div className="relative my-3 min-h-[min(24dvh,200px)] flex-1 overflow-hidden rounded-2xl bg-black landscape:col-start-1 landscape:row-start-2 landscape:my-0 landscape:min-h-0 landscape:h-full" style={{ containerType: 'size' }}>
            <video ref={videoRef} autoPlay muted playsInline aria-label="실시간 카메라"
              onPlaying={(event) => { setReady(true); setVideoAspect(event.currentTarget.videoWidth / event.currentTarget.videoHeight || 4 / 3); }}
              className="absolute inset-0 h-full w-full object-contain" />
            <div data-testid="camera-capture-guide" aria-hidden style={{ width: `min(86cqw, ${86 * videoAspect}cqh)`, aspectRatio: videoAspect }}
              className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-white/30">
              <span className="absolute -left-0.5 -top-0.5 size-8 rounded-tl-lg border-l-4 border-t-4 border-white" />
              <span className="absolute -right-0.5 -top-0.5 size-8 rounded-tr-lg border-r-4 border-t-4 border-white" />
              <span className="absolute -bottom-0.5 -left-0.5 size-8 rounded-bl-lg border-b-4 border-l-4 border-white" />
              <span className="absolute -bottom-0.5 -right-0.5 size-8 rounded-br-lg border-b-4 border-r-4 border-white" />
            </div>
            {!ready && !error && <p role="status" className="absolute inset-0 grid place-items-center px-8 text-center text-sm">카메라를 연결하고 있어요…</p>}
            {error && <div role="alert" className="absolute inset-0 flex items-center justify-center bg-slate-950/95 p-8 text-center text-base leading-relaxed">{error}</div>}
          </div>

          <div className="shrink-0 landscape:col-start-2 landscape:row-start-2 landscape:min-h-0 landscape:overflow-y-auto">
          {ready && !error && (zoom ? <div className="mb-3 rounded-xl bg-white/10 px-3 py-2">
            <label htmlFor="camera-zoom" className="flex justify-between text-sm"><span>촬영 배율</span><output>{zoom.value.toFixed(1)}×</output></label>
            <input id="camera-zoom" type="range" aria-label="촬영 배율" min={zoom.min} max={zoom.max} step={zoom.step} value={zoom.value}
              disabled={zooming || capturing} onChange={(event) => void changeZoom(Number(event.target.value))}
              className="h-11 w-full accent-teal-400" />
          </div> : <p className="mb-3 text-center text-sm text-slate-300">배율 조절은 기본 카메라에서 이용해주세요.</p>)}
          {zoomHint && <p role="status" className="mb-3 text-center text-sm text-teal-200">{zoomHint}</p>}
          <button type="button" onClick={() => void toggleLandscape()} disabled={rotating} aria-pressed={landscapeRequested}
            className="mb-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-white/10 px-3 text-sm font-medium disabled:opacity-50 focus-visible:outline focus-visible:outline-white">
            <RotateCw aria-hidden className="size-4" />{landscapeRequested ? '자동 회전으로 돌아가기' : '가로 촬영으로 전환'}
          </button>
          {rotationHint && <p role="status" className="mb-3 text-center text-sm leading-relaxed text-teal-200">{rotationHint}</p>}
          <p className="shrink-0 text-center text-sm leading-relaxed text-slate-300 landscape:hidden">밝은 곳에서 종이를 평평하게 펴고<br />글자에 초점을 맞춘 뒤 촬영해주세요.</p>
          <div className="my-4 flex shrink-0 justify-center">
            <button type="button" aria-label="사진 촬영" disabled={!ready || capturing || zooming || Boolean(error)} onClick={() => void capturePhoto()}
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
