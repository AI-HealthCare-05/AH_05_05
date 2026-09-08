import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { Dialog, DialogClose, DialogContent, DialogTitle } from './dialog';

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
 * 이미지의 기본 확대 제스처를 막지 않도록 touch-action을 auto로 유지합니다.
 */
export function ImageViewer({
  open,
  src,
  title,
  alt = '확대한 약봉투 원본',
  toolbar,
  onOpenChange,
}: ImageViewerProps) {
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
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <img
            src={src}
            alt={alt}
            className="max-h-full w-auto max-w-full object-contain"
            style={{ touchAction: 'auto' }}
            onClick={() => onOpenChange(false)}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
