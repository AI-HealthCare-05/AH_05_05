import { useEffect, useRef, useState } from 'react';
import { Camera, ImageIcon, RotateCw, X } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/shared/ui/dialog';
import { classifyLensLabel, parseGenericCameraLabel, type GenericCameraLabel, type LensKind } from './selectRearCamera';

interface GuidedCameraProps {
  onCapture: (file: File) => void;
  onClose: () => void;
  onNativeCamera: () => void;
  onGallery: () => void;
}

type ZoomRange = { min: number; max: number; step: number; value: number };
type CameraCapabilities = MediaTrackCapabilities & {
  zoom?: { min: number; max: number; step?: number };
  focusMode?: string[];
  exposureMode?: string[];
  whiteBalanceMode?: string[];
};
type CameraSettings = MediaTrackSettings & { zoom?: number; deviceId?: string };
type StillCamera = {
  takePhoto: (settings?: { imageWidth: number; imageHeight: number }) => Promise<Blob>;
  getPhotoCapabilities?: () => Promise<{ imageWidth: { max: number }; imageHeight: { max: number } }>;
};
type StillCameraConstructor = new (track: MediaStreamTrack) => StillCamera;

// Corner guide tracks the live video's own aspect, inset this fraction from each edge (5-7% target).
const GUIDE_INSET_RATIO = 0.06;
const GUIDE_SCALE = 100 * (1 - 2 * GUIDE_INSET_RATIO);
// Give automatic camera controls time to settle; this is not a sharpness guarantee.
const CAMERA_SETTLE_MS = 600;
// Match app/services/ocr_image_input.py; keep supported photo bytes unchanged.
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const MAX_IMAGE_EDGE = 10000;
const MAX_IMAGE_PIXELS = 40_000_000;
// Requested only after the physical camera/lens is settled, via applyConstraints on the already-open
// track — never as part of the initial getUserMedia/deviceId request, so a resolution preference can
// never bias which physical lens facingMode/enumerateDevices ends up choosing.
const PREFERRED_RESOLUTION: MediaTrackConstraints = { width: { ideal: 4096 }, height: { ideal: 3072 } };
// Bumped whenever the rear-camera selection/zoom logic changes, so a field report's debug JSON can be
// matched against a known revision instead of guessing what code is actually deployed on the device.
const CAMERA_LOGIC_REVISION = 'rear-camera-r7-generic-camera0-fallback';

// Diagnostics-only: never touches deviceId/groupId, frames, photos, or app/patient data, and never
// leaves the device (no network calls, no storage). Only active behind ?cameraDebug=1.
type CameraDebugVideoInput = { index: number; label: string; selected: boolean; classification: LensKind };
type CameraDebugSnapshot = {
  generatedAt: string;
  userAgent: string;
  secureContext: boolean;
  revision: string;
  videoInputs: CameraDebugVideoInput[];
  enumerateDevicesError?: string;
  track?: { label: string; facingMode?: string; width?: number; height?: number };
  zoomCapability?: { min: number; max: number; step?: number };
  actualZoom?: number;
  constraintZoomAfterResolution?: number;
  lastError?: string;
  selectionReason?: string;
};

function isCameraDebugEnabled() {
  if (typeof window === 'undefined') return false;
  try {
    return new URLSearchParams(window.location.search).get('cameraDebug') === '1';
  } catch {
    return false;
  }
}

function isSupportedSize(width: number, height: number) {
  return width > 0 && height > 0 && width <= MAX_IMAGE_EDGE && height <= MAX_IMAGE_EDGE
    && width * height <= MAX_IMAGE_PIXELS;
}

async function isSupportedPhoto(photo: Blob) {
  if (!photo.size || photo.size > MAX_UPLOAD_BYTES || !['image/jpeg', 'image/png'].includes(photo.type)) return false;
  const url = URL.createObjectURL(photo);
  const image = new Image();
  try {
    return await new Promise<boolean>((resolve) => {
      image.onload = () => resolve(isSupportedSize(image.naturalWidth, image.naturalHeight));
      image.onerror = () => resolve(false);
      image.src = url;
    });
  } finally {
    image.onload = null;
    image.onerror = null;
    image.src = '';
    URL.revokeObjectURL(url);
  }
}

export function GuidedCamera({ onCapture, onClose, onNativeCamera, onGallery }: GuidedCameraProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const trackRef = useRef<MediaStreamTrack | null>(null);
  const activeStreamRef = useRef<MediaStream | undefined>(undefined);
  // Which physical camera is currently open, and a re-entrancy guard for switching between them. Not
  // React state: nothing renders from these, they only drive internal getUserMedia bookkeeping.
  const activeDeviceIdRef = useRef<string | undefined>(undefined);
  const switchingLensRef = useRef(false);
  const capturePendingRef = useRef(false);
  const activeRef = useRef(false);
  const settleTimerRef = useRef<number | undefined>(undefined);
  const displayRef = useRef({ fullscreen: false, locked: false });
  // Diagnostics-only (see isCameraDebugEnabled/CameraDebugSnapshot): the last relevant error name and
  // the reason refineRearCamera did or didn't switch devices, kept regardless of debug mode (cheap ref
  // writes) so they're available if the debug panel is opened after the fact.
  const lastCameraErrorRef = useRef<string>('');
  const lastSelectionReasonRef = useRef<string>('not-yet-evaluated');
  const debugTextareaRef = useRef<HTMLTextAreaElement>(null);
  const [ready, setReady] = useState(false);
  const [settling, setSettling] = useState(true);
  const [lowPreviewResolution, setLowPreviewResolution] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState('');
  const [landscapeRequested, setLandscapeRequested] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [rotationHint, setRotationHint] = useState('');
  const [zoom, setZoom] = useState<ZoomRange | null>(null);
  const [zooming, setZooming] = useState(false);
  const [zoomHint, setZoomHint] = useState('');
  const [videoAspect, setVideoAspect] = useState(4 / 3);
  const [debugSnapshot, setDebugSnapshot] = useState<CameraDebugSnapshot | null>(null);
  const [debugCopyHint, setDebugCopyHint] = useState('');

  function settleCamera() {
    window.clearTimeout(settleTimerRef.current);
    setSettling(true);
    settleTimerRef.current = window.setTimeout(() => {
      settleTimerRef.current = undefined;
      if (activeRef.current) setSettling(false);
    }, CAMERA_SETTLE_MS);
  }

  // A ref-based useEffect(() => { videoRef.current ... }, []) is unreliable here: Radix's Dialog
  // portal can commit the <video> node on a later pass than this component's first effect flush, so
  // the ref reads null and the listener never attaches (onPlaying still worked because React wires
  // JSX event props into the same commit that creates the node, regardless of portal timing). Using
  // React's own onLoadedMetadata/onResize video props sidesteps that entirely — they attach exactly
  // like onPlaying already does. onResize also covers a device rotation that changes the SAME live
  // track's intrinsic size without ever firing a new `playing` event (only `resize` fires for that).
  function syncVideoDimensions() {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) return;
    setVideoAspect(video.videoWidth / video.videoHeight);
    setLowPreviewResolution(Math.max(video.videoWidth, video.videoHeight) < 1600);
  }

  // Baselines the picked lens at its native 1x (zoom=1 is "no zoom" per the Media Capture spec) instead
  // of whatever the device defaulted to. This matters even without any lens-selection mismatch: some
  // phones expose a single fused rear camera whose zoom range spans below 1x (a hardware-fused ultrawide
  // crop) and default the stream to range.min, which is the actual root cause on at least some Galaxy
  // devices — the browser never exposes a separate "ultrawide" device to pick around in that case.
  async function applyTrackFeatures(track: MediaStreamTrack) {
    try {
      const capabilities = track.getCapabilities?.() as CameraCapabilities | undefined;
      const range = capabilities?.zoom;
      if (range && Number.isFinite(range.min) && Number.isFinite(range.max) && range.min > 0 && range.max > range.min) {
        if (range.min <= 1 && range.max >= 1) {
          try { await track.applyConstraints({ advanced: [{ zoom: 1 } as MediaTrackConstraintSet] }); } catch { /* Keep the device default when 1x is rejected. */ }
        }
        if (!activeRef.current) return;
        const settledZoom = (track.getSettings() as CameraSettings).zoom;
        setZoom({
          min: range.min, max: range.max, step: range.step && range.step > 0 ? range.step : 0.1,
          value: settledZoom ?? (range.min <= 1 && range.max >= 1 ? 1 : range.min),
        });
      } else if (activeRef.current) {
        setZoom(null);
      }
      // Request only advertised modes, independently: one rejected control must not disable others.
      for (const mode of ['focusMode', 'exposureMode', 'whiteBalanceMode'] as const) {
        if (!activeRef.current) return;
        if (capabilities?.[mode]?.includes('continuous')) {
          try { await track.applyConstraints({ advanced: [{ [mode]: 'continuous' } as MediaTrackConstraintSet] }); } catch { /* Keep the device default when an optional control is rejected. */ }
        }
      }
    } catch { /* Camera controls are optional; the live stream remains usable. */ }
  }

  // Applies the current physical camera's stream to the <video> element and best-effort upgrades its
  // resolution afterward (never as part of the initial device request — see PREFERRED_RESOLUTION).
  async function adoptStream(nextStream: MediaStream, deviceId: string | undefined) {
    activeStreamRef.current = nextStream;
    const track = nextStream.getVideoTracks()[0];
    trackRef.current = track ?? null;
    activeDeviceIdRef.current = deviceId;
    const video = videoRef.current;
    if (video) {
      video.srcObject = nextStream;
      try { await video.play(); } catch { /* onPlaying/error UI already cover playback issues */ }
    }
    if (track) {
      await applyTrackFeatures(track);
      if (activeRef.current) {
        try { await track.applyConstraints(PREFERRED_RESOLUTION); } catch { /* Keep whatever resolution the device already opened at. */ }
      }
    }
  }

  // Reopens the preview on a specific physical camera identified via enumerateDevices. Many phones
  // cannot hold two camera sessions open at once, so the current one is deliberately released before
  // requesting the next — if that request then fails, this rolls back to the previous device instead
  // of leaving the preview blank or broken.
  async function switchToDeviceId(deviceId: string) {
    if (!activeRef.current || switchingLensRef.current || deviceId === activeDeviceIdRef.current) return;
    const previousDeviceId = activeDeviceIdRef.current;
    const previousStream = activeStreamRef.current;
    switchingLensRef.current = true;
    settleCamera();
    previousStream?.getTracks().forEach((track) => track.stop());
    activeStreamRef.current = undefined;
    trackRef.current = null;
    try {
      const next = await navigator.mediaDevices.getUserMedia({ audio: false, video: { deviceId: { exact: deviceId } } });
      if (!activeRef.current) { next.getTracks().forEach((track) => track.stop()); return; }
      await adoptStream(next, deviceId);
    } catch (cause) {
      lastCameraErrorRef.current = cause instanceof Error ? cause.name : 'UnknownError';
      // The target device could not be opened (e.g. this phone only allows one camera session at a
      // time and the release didn't free it up in time, or the device disappeared) — roll back to
      // whichever camera was already working rather than leaving the preview stuck on nothing.
      if (activeRef.current && previousDeviceId) {
        try {
          const restored = await navigator.mediaDevices.getUserMedia({ audio: false, video: { deviceId: { exact: previousDeviceId } } });
          if (!activeRef.current) { restored.getTracks().forEach((track) => track.stop()); return; }
          await adoptStream(restored, previousDeviceId);
        } catch (restoreCause) {
          lastCameraErrorRef.current = restoreCause instanceof Error ? restoreCause.name : 'UnknownError';
          if (activeRef.current) setError('카메라를 전환하지 못했어요. 기본 카메라나 저장된 사진으로도 등록할 수 있어요.');
        }
      }
    } finally {
      switchingLensRef.current = false;
    }
  }

  // Diagnostics-only (behind ?cameraDebug=1): reads the live track's current settings/capabilities and
  // enumerates devices for labels/classification. Never opens, closes, or replaces any stream itself.
  async function gatherCameraDebugSnapshot(): Promise<CameraDebugSnapshot> {
    const track = trackRef.current;
    const settings = track?.getSettings?.() as CameraSettings | undefined;
    const capabilities = track?.getCapabilities?.() as CameraCapabilities | undefined;

    let constraintZoomAfterResolution: number | undefined;
    try {
      type ZoomConstraintSet = MediaTrackConstraintSet & { zoom?: number };
      const constraints = track?.getConstraints?.() as (MediaTrackConstraints & { advanced?: ZoomConstraintSet[] }) | undefined;
      for (const entry of constraints?.advanced ?? []) {
        if (typeof entry.zoom === 'number') constraintZoomAfterResolution = entry.zoom;
      }
    } catch { /* getConstraints is an optional diagnostic detail. */ }

    let videoInputs: CameraDebugVideoInput[] = [];
    let enumerateDevicesError: string | undefined;
    if (navigator.mediaDevices?.enumerateDevices) {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        videoInputs = devices
          .filter((device) => device.kind === 'videoinput')
          .map((device, index) => ({
            index,
            label: device.label || '(label unavailable)',
            selected: device.deviceId === activeDeviceIdRef.current,
            classification: classifyLensLabel(device.label),
          }));
      } catch (cause) {
        enumerateDevicesError = cause instanceof Error ? cause.name : String(cause);
      }
    } else {
      enumerateDevicesError = 'enumerateDevices unavailable';
    }

    return {
      generatedAt: new Date().toISOString(),
      userAgent: navigator.userAgent,
      secureContext: window.isSecureContext,
      revision: CAMERA_LOGIC_REVISION,
      videoInputs,
      enumerateDevicesError,
      track: track ? { label: track.label, facingMode: settings?.facingMode, width: settings?.width, height: settings?.height } : undefined,
      zoomCapability: capabilities?.zoom
        ? { min: capabilities.zoom.min, max: capabilities.zoom.max, step: capabilities.zoom.step }
        : undefined,
      actualZoom: settings?.zoom,
      constraintZoomAfterResolution,
      lastError: lastCameraErrorRef.current || undefined,
      selectionReason: lastSelectionReasonRef.current,
    };
  }

  async function refreshCameraDebugSnapshot() {
    const snapshot = await gatherCameraDebugSnapshot();
    if (activeRef.current) setDebugSnapshot(snapshot);
  }

  async function copyCameraDebugSnapshot() {
    if (!debugSnapshot) return;
    const text = JSON.stringify(debugSnapshot, null, 2);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        setDebugCopyHint('클립보드에 복사했어요.');
        return;
      }
    } catch { /* Fall through to the manual-selection fallback below. */ }
    const textarea = debugTextareaRef.current;
    if (textarea) {
      textarea.focus();
      textarea.select();
    }
    setDebugCopyHint('자동 복사를 사용할 수 없어요. 아래 텍스트가 선택되었으니 직접 복사해주세요.');
  }

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
      settleCamera();
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

    // Web APIs expose no native-equivalent focal length or lens identity, so this is a best-effort
    // correction, not a guarantee. Two tiers, in priority order:
    //  1. Descriptive-label match: unless the current device's label already confidently reads as the
    //     main/wide lens, look for exactly one unambiguous "main"-labeled alternative and switch to it.
    //     A generic/opaque current label (common on Android) must not block this — it is not evidence
    //     the current pick is correct, just unreadable.
    //  2. Bounded generic-id fallback: only when tier 1 found nothing at all (no descriptive "main"
    //     label anywhere). Confirmed on a real Galaxy S26 Ultra / Samsung Internet device: every rear
    //     camera was exposed only as "camera N, facing back" with zero lens-descriptive text, so tier 1
    //     can never resolve it. By a common (not spec-guaranteed) Android Camera2 convention, id 0 is
    //     the primary rear sensor — if there are multiple such generically-labeled rear cameras and
    //     exactly one reports id 0, switch to it. This is a heuristic backed by that one supplied
    //     device's evidence, not a universal optical guarantee, and a bare "facing back" label is still
    //     never treated as confirmed 'main' (classifyLensLabel never returns 'main' for it).
    // Anything still uncertain after both tiers is left alone: there is no lens picker to punt this to
    // anymore, and guessing wrong is worse than leaving the facingMode default in place.
    async function refineRearCamera(initialTrack: MediaStreamTrack) {
      if (!navigator.mediaDevices.enumerateDevices) { lastSelectionReasonRef.current = 'enumerateDevices-unavailable'; return; }
      let devices: MediaDeviceInfo[];
      try {
        devices = await navigator.mediaDevices.enumerateDevices();
      } catch {
        lastSelectionReasonRef.current = 'enumerateDevices-failed';
        return;
      }
      if (cancelled || !activeRef.current) return;
      const videoInputs = devices.filter((device) => device.kind === 'videoinput' && device.deviceId);
      if (videoInputs.length <= 1) { lastSelectionReasonRef.current = 'single-camera-no-choice'; return; }
      if (classifyLensLabel(initialTrack.label) === 'main') { lastSelectionReasonRef.current = 'current-already-main-label'; return; }

      const currentDeviceId = activeDeviceIdRef.current;
      const mainCandidates = videoInputs.filter((device) =>
        device.deviceId !== currentDeviceId && classifyLensLabel(device.label) === 'main');
      if (mainCandidates.length === 1) {
        lastSelectionReasonRef.current = 'switched-to-main-label-match';
        await switchToDeviceId(mainCandidates[0].deviceId);
        return;
      }
      if (mainCandidates.length > 1) { lastSelectionReasonRef.current = 'ambiguous-multiple-main-labels-no-switch'; return; }

      const rearGeneric = videoInputs
        .map((device) => ({ device, parsed: parseGenericCameraLabel(device.label) }))
        .filter((entry): entry is { device: MediaDeviceInfo; parsed: GenericCameraLabel } =>
          entry.parsed !== null && entry.parsed.facing === 'back');
      const zeroIdElsewhere = rearGeneric.filter((entry) => entry.parsed.id === 0 && entry.device.deviceId !== currentDeviceId);
      if (rearGeneric.length > 1 && zeroIdElsewhere.length === 1) {
        lastSelectionReasonRef.current = 'switched-to-generic-camera0-fallback';
        await switchToDeviceId(zeroIdElsewhere[0].device.deviceId);
        return;
      }
      if (rearGeneric.some((entry) => entry.parsed.id === 0 && entry.device.deviceId === currentDeviceId)) {
        lastSelectionReasonRef.current = 'current-already-generic-camera0';
        return;
      }
      lastSelectionReasonRef.current = rearGeneric.length > 1
        ? 'generic-labels-no-unique-camera0-no-switch'
        : 'no-confident-candidate-no-switch';
    }

    async function startCamera() {
      try {
        // No resolution constraint here on purpose: asking for 4096x3072 up front can steer the
        // browser/OS toward whichever physical lens can hit that resolution, which is not necessarily
        // the main lens. Resolution is upgraded afterward, once the lens itself is settled.
        const opened = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: 'environment' } },
        });
        if (cancelled) {
          opened.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = opened;
        activeStreamRef.current = opened;
        const track = opened.getVideoTracks()[0];
        trackRef.current = track ?? null;
        activeDeviceIdRef.current = track ? (track.getSettings() as CameraSettings).deviceId : undefined;
        if (track) await applyTrackFeatures(track);
        if (cancelled) return;
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = opened;
        await video.play();
        if (track) await refineRearCamera(track);
        if (!cancelled && activeRef.current && trackRef.current) {
          try { await trackRef.current.applyConstraints(PREFERRED_RESOLUTION); } catch { /* Keep whatever resolution the device already opened at. */ }
        }
      } catch (cause) {
        if (cancelled) return;
        stream?.getTracks().forEach((track) => track.stop());
        const name = cause instanceof Error ? cause.name : '';
        lastCameraErrorRef.current = name || 'UnknownError';
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
      window.clearTimeout(settleTimerRef.current);
      trackRef.current = null;
      activeStreamRef.current?.getTracks().forEach((track) => track.stop());
      activeStreamRef.current = undefined;
      releaseDisplay();
      document.removeEventListener('visibilitychange', closeWhenHidden);
    };
  }, [onClose]);

  const guidanceText = settling
    ? '잠시 흔들림 없이 기다려주세요…'
    : lowPreviewResolution
      ? '미리보기 해상도가 낮아요. 기본 카메라 촬영을 권장해요.'
      : '네 모서리를 맞추고 글자가 선명하면 촬영하세요.';

  async function capturePhoto() {
    const video = videoRef.current;
    if (!video || !ready || settling || capturePendingRef.current || zooming || !video.videoWidth || !video.videoHeight) return;
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
            if (Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0) {
              const scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(width, height), Math.sqrt(MAX_IMAGE_PIXELS / (width * height)));
              settings = { imageWidth: Math.floor(width * scale), imageHeight: Math.floor(height * scale) };
            }
          } catch { /* Default photo settings are still usable. */ }
          if (!activeRef.current) return;
          let photo: Blob;
          try {
            photo = await camera.takePhoto(settings);
          } catch (cause) {
            if (!settings || !activeRef.current) throw cause;
            // Some devices reject a requested size but still support a full-quality default exposure.
            photo = await camera.takePhoto();
          }
          if (!activeRef.current) return;
          if (await isSupportedPhoto(photo)) {
            if (!activeRef.current) return;
            onCapture(new File([photo], `medication-${Date.now()}.${photo.type === 'image/png' ? 'png' : 'jpg'}`, { type: photo.type }));
            return;
          }
        } catch { /* Fall back to the complete native video frame when still capture is unavailable. */ }
      }
      if (!activeRef.current) return;
      if (!isSupportedSize(video.videoWidth, video.videoHeight)) throw new Error('Video exceeds image limits');
      const canvas = document.createElement('canvas');
      try {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Canvas unavailable');
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.98));
        if (!activeRef.current) return;
        if (!blob || blob.size > MAX_UPLOAD_BYTES) throw new Error('Photo encoding failed or exceeds image limits');
        onCapture(new File([blob], `medication-${Date.now()}.jpg`, { type: 'image/jpeg' }));
      } finally {
        // Release the high-resolution pixel buffer immediately, including when the dialog was closed.
        canvas.width = 0;
        canvas.height = 0;
      }
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
        className="inset-0 left-0 top-0 flex h-dvh w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-y-auto rounded-none border-0 bg-black p-0 text-white"
      >
        <div className="mx-auto flex h-full min-h-0 w-full max-w-lg flex-col px-4 pt-[max(0.5rem,env(safe-area-inset-top))] pb-[max(0.5rem,env(safe-area-inset-bottom))] landscape:grid landscape:h-full landscape:min-h-0 landscape:max-w-none landscape:grid-cols-[minmax(0,1fr)_152px] landscape:grid-rows-[minmax(0,1fr)] landscape:gap-x-3 landscape:px-3 landscape:pt-[max(0.5rem,env(safe-area-inset-top))] landscape:pb-[max(0.5rem,env(safe-area-inset-bottom))]">
          {/* landscape:min-h-0 collapses this to zero height (its only landscape content is the sr-only
              title, which is position:absolute and takes no space) instead of reserving a title row. */}
          <header className="relative flex min-h-9 shrink-0 items-center justify-center landscape:min-h-0">
            <DialogTitle className="text-lg text-white landscape:sr-only">약봉투 촬영</DialogTitle>
            <button type="button" aria-label="카메라 닫기" onClick={onClose} className="absolute right-0 flex size-11 items-center justify-center rounded-full bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white landscape:hidden">
              <X aria-hidden className="size-5" />
            </button>
          </header>
          <DialogDescription className="mt-1 text-center text-sm text-slate-300 landscape:sr-only">
            문서의 네 모서리가 잘리지 않게 담아주세요. 사진 전체가 저장돼요.
          </DialogDescription>

          <div data-testid="camera-preview-frame" className="relative my-2 min-h-[min(20dvh,160px)] flex-1 overflow-hidden rounded-2xl bg-black landscape:col-start-1 landscape:row-start-1 landscape:my-0 landscape:min-h-0 landscape:h-full" style={{ containerType: 'size' }}>
            <video ref={videoRef} autoPlay muted playsInline aria-label="실시간 카메라"
              onLoadedMetadata={syncVideoDimensions}
              onResize={() => { settleCamera(); syncVideoDimensions(); }}
              onPlaying={() => { setReady(true); settleCamera(); syncVideoDimensions(); }}
              className="absolute inset-0 h-full w-full object-contain" />
            <div data-testid="camera-capture-guide" aria-hidden style={{
              width: `min(${GUIDE_SCALE}cqw, ${GUIDE_SCALE * videoAspect}cqh)`,
              aspectRatio: videoAspect,
            }}
              className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-white/30">
              <span className="absolute -left-0.5 -top-0.5 size-8 rounded-tl-lg border-l-4 border-t-4 border-white" />
              <span className="absolute -right-0.5 -top-0.5 size-8 rounded-tr-lg border-r-4 border-t-4 border-white" />
              <span className="absolute -bottom-0.5 -left-0.5 size-8 rounded-bl-lg border-b-4 border-l-4 border-white" />
              <span className="absolute -bottom-0.5 -right-0.5 size-8 rounded-br-lg border-b-4 border-r-4 border-white" />
            </div>
            {!ready && !error && <p role="status" className="absolute inset-0 grid place-items-center px-8 text-center text-sm">카메라를 연결하고 있어요…</p>}
            {error && <div role="alert" className="absolute inset-0 flex items-center justify-center bg-black/95 p-8 text-center text-base leading-relaxed">{error}</div>}
            <button type="button" aria-label="카메라 닫기" onClick={onClose} className="absolute right-2 top-2 hidden size-9 items-center justify-center rounded-full bg-black/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white landscape:flex">
              <X aria-hidden className="size-4" />
            </button>
          </div>

          {/* landscape:justify-between spreads the three groups across the full column height (top
              cluster, shutter, secondary actions) instead of leaving them packed at the top with a big
              blank gap below on tall landscape screens. Short screens still shrink via overflow-y-auto. */}
          <div data-testid="camera-controls" className="min-h-0 shrink-0 landscape:col-start-2 landscape:row-start-1 landscape:flex landscape:h-full landscape:flex-col landscape:justify-between landscape:overflow-y-auto">
          <div>
          {ready && !error && <p data-testid="camera-guidance" role="status" className="mt-1.5 shrink-0 text-center text-xs leading-snug text-slate-300 landscape:mt-0">{guidanceText}</p>}
          {ready && !error && (zoom ? <div className="mb-2 rounded-xl bg-white/10 px-3 py-1.5 landscape:mb-1 landscape:px-2 landscape:py-1">
            <label htmlFor="camera-zoom" className="flex justify-between text-sm landscape:text-xs"><span>촬영 배율</span><output>{zoom.value.toFixed(1)}×</output></label>
            <input id="camera-zoom" type="range" aria-label="촬영 배율" min={zoom.min} max={zoom.max} step={zoom.step} value={zoom.value}
              disabled={zooming || capturing} onChange={(event) => void changeZoom(Number(event.target.value))}
              className="h-9 w-full accent-teal-400 landscape:h-6" />
          </div> : <p className="mb-2 text-center text-sm text-slate-300 landscape:mb-1 landscape:text-xs">배율 조절은 기본 카메라에서 이용해주세요.</p>)}
          {zoomHint && <p role="status" className="mb-2 text-center text-sm text-teal-200 landscape:mb-1 landscape:text-xs">{zoomHint}</p>}
          <button type="button" data-testid="camera-rotate-toggle" onClick={() => void toggleLandscape()} disabled={rotating} aria-pressed={landscapeRequested}
            className="mb-2 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-white/10 px-3 text-sm font-medium disabled:opacity-50 focus-visible:outline focus-visible:outline-white landscape:mb-1 landscape:min-h-9 landscape:px-2 landscape:text-xs">
            <RotateCw aria-hidden className="size-4" />{landscapeRequested ? '자동 회전으로 돌아가기' : '가로 촬영으로 전환'}
          </button>
          {rotationHint && <p role="status" className="mb-2 text-center text-sm leading-relaxed text-teal-200 landscape:mb-1 landscape:text-xs landscape:leading-snug">{rotationHint}</p>}
          </div>
          <div className="my-2 flex shrink-0 justify-center landscape:my-1">
            <button type="button" aria-label="사진 촬영" disabled={!ready || settling || capturing || zooming || Boolean(error)} onClick={() => void capturePhoto()}
              className="flex size-20 items-center justify-center rounded-full border-4 border-white p-1.5 shadow-lg focus-visible:outline focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-white disabled:opacity-40">
              <span className="flex size-full items-center justify-center rounded-full bg-primary shadow-inner"><Camera aria-hidden className="size-8 text-white" /></span>
            </button>
          </div>
          <div className="flex shrink-0 justify-center gap-3 landscape:grid landscape:grid-cols-2 landscape:gap-1.5">
            <button type="button" onClick={onNativeCamera} className="min-h-11 rounded-xl bg-white/10 px-3 text-sm font-medium focus-visible:outline focus-visible:outline-white landscape:min-h-9 landscape:px-1 landscape:text-xs">일반 카메라로 전환</button>
            <button type="button" onClick={onGallery} className="flex min-h-11 items-center justify-center gap-2 rounded-xl bg-white/10 px-3 text-sm font-medium focus-visible:outline focus-visible:outline-white landscape:min-h-9 landscape:px-1 landscape:text-xs">
              <ImageIcon aria-hidden className="size-4 landscape:hidden" />사진에서 선택
            </button>
          </div>
          </div>
        </div>
        {/* Diagnostics only, behind ?cameraDebug=1 — absent from the normal UI entirely (not just
            hidden). Fixed positioning keeps it out of the portrait/landscape grid so it can never
            affect ordinary layout, and it never opens/closes/replaces the live stream itself. */}
        {isCameraDebugEnabled() && (
          <details className="fixed inset-x-2 bottom-[max(0.5rem,env(safe-area-inset-bottom))] z-50 max-h-[40dvh] overflow-auto rounded-xl bg-black/90 p-2 text-xs text-slate-100 shadow-lg"
            onToggle={(event) => { if (event.currentTarget.open) void refreshCameraDebugSnapshot(); }}>
            <summary className="cursor-pointer select-none font-medium">카메라 진단 정보 (디버그)</summary>
            <div className="mt-2 space-y-2">
              <div className="flex gap-2">
                <button type="button" onClick={() => void refreshCameraDebugSnapshot()} className="rounded-lg bg-white/10 px-2 py-1">새로고침</button>
                <button type="button" onClick={() => void copyCameraDebugSnapshot()} className="rounded-lg bg-white/10 px-2 py-1">복사</button>
              </div>
              {debugCopyHint && <p role="status" className="text-teal-200">{debugCopyHint}</p>}
              <textarea readOnly ref={debugTextareaRef} aria-label="카메라 진단 정보"
                value={debugSnapshot ? JSON.stringify(debugSnapshot, null, 2) : '펼치거나 새로고침을 눌러 정보를 불러오세요.'}
                onFocus={(event) => event.currentTarget.select()}
                className="h-40 w-full resize-none rounded-lg bg-black/60 p-2 font-mono text-[10px] leading-snug text-slate-100" />
            </div>
          </details>
        )}
      </DialogContent>
    </Dialog>
  );
}
