import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { X, ZoomIn, ZoomOut } from 'lucide-react';
import { Dialog, DialogClose, DialogContent, DialogTitle } from './dialog';

const IMAGE_VIEWER_ZOOM_LEVELS = [1, 1.5, 2, 3] as const;

export interface ImageViewerProps {
  open: boolean;
  src: string;
  title: string;
  alt?: string;
  toolbar?: ReactNode;
  onOpenChange: (open: boolean) => void;
}

/**
 * 등록 문서 원본을 화면 가득 확인하는 뷰어입니다.
 * 맞춤 확대 단계와 스크롤 이동으로 작은 글자를 확인할 수 있습니다.
 */
export function ImageViewer({
  open,
  src,
  title,
  alt = '확대한 약봉투 원본',
  toolbar,
  onOpenChange,
}: ImageViewerProps) {
  const [zoomIndex, setZoomIndex] = useState(0);
  const [fittedSize, setFittedSize] = useState<{ width: number; height: number } | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const zoom = IMAGE_VIEWER_ZOOM_LEVELS[zoomIndex];
  const scaledSize = fittedSize
    ? { width: fittedSize.width * zoom, height: fittedSize.height * zoom }
    : null;

  function measureFittedSize() {
    const area = scrollAreaRef.current;
    const image = imageRef.current;
    if (!area || !image || image.naturalWidth === 0 || image.naturalHeight === 0) return;
    const areaBox = area.getBoundingClientRect();
    const fit = Math.min(
      areaBox.width / image.naturalWidth,
      areaBox.height / image.naturalHeight,
      1,
    );
    const next = {
      width: image.naturalWidth * fit,
      height: image.naturalHeight * fit,
    };
    setFittedSize((current) =>
      current &&
      Math.abs(current.width - next.width) < 0.5 &&
      Math.abs(current.height - next.height) < 0.5
        ? current
        : next,
    );
  }

  useEffect(() => {
    if (open) {
      setZoomIndex(0);
      setFittedSize(null);
    }
  }, [open, src]);

  useLayoutEffect(() => {
    if (!open || !scrollAreaRef.current) return undefined;
    measureFittedSize();
    const observer = new ResizeObserver(measureFittedSize);
    observer.observe(scrollAreaRef.current);
    return () => observer.disconnect();
  }, [open, src]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="inset-0 left-0 top-0 flex h-dvh w-screen max-w-none translate-x-0 translate-y-0 flex-col overflow-hidden rounded-none border-0 bg-foreground p-4"
      >
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <div className="relative flex min-h-12 shrink-0 items-center justify-center pr-14 sm:px-14">
          {toolbar}
          <DialogClose
            aria-label="닫기"
            className="absolute right-0 top-0 flex size-12 items-center justify-center rounded-full bg-white text-slate-900 shadow-lg transition-colors hover:bg-slate-200 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
          >
            <X className="size-7" strokeWidth={2.5} aria-hidden />
          </DialogClose>
        </div>
        <div
          ref={scrollAreaRef}
          role="region"
          tabIndex={0}
          aria-label="확대한 약봉투 이동 영역"
          className="min-h-0 flex-1 overflow-auto overscroll-contain rounded-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
          style={{ touchAction: 'pan-x pan-y pinch-zoom' }}
        >
          <div
            className="grid min-h-full min-w-full place-items-center"
            style={scaledSize ? { width: scaledSize.width, height: scaledSize.height } : undefined}
          >
            <img
              ref={imageRef}
              src={src}
              alt={alt}
              draggable={false}
              className={scaledSize ? 'block max-w-none object-contain' : 'max-h-full w-auto max-w-full object-contain'}
              style={scaledSize ? { width: scaledSize.width, height: scaledSize.height } : undefined}
              onLoad={measureFittedSize}
            />
          </div>
        </div>
        <div
          role="group"
          aria-label="이미지 확대 축소"
          className="mx-auto flex min-h-12 shrink-0 items-center gap-1 rounded-full bg-background/95 p-1 text-foreground shadow-card"
        >
          <button
            type="button"
            aria-label="축소"
            disabled={zoomIndex === 0}
            className="flex size-touch items-center justify-center rounded-full disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setZoomIndex((index) => Math.max(0, index - 1))}
          >
            <ZoomOut aria-hidden className="size-5" />
          </button>
          <span role="status" aria-label="확대 비율" className="min-w-14 text-center text-sm font-bold tnum">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            aria-label="확대"
            disabled={zoomIndex === IMAGE_VIEWER_ZOOM_LEVELS.length - 1}
            className="flex size-touch items-center justify-center rounded-full disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setZoomIndex((index) => Math.min(IMAGE_VIEWER_ZOOM_LEVELS.length - 1, index + 1))}
          >
            <ZoomIn aria-hidden className="size-5" />
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
