import type { ReactNode } from 'react';
import { Dialog, DialogContent, DialogTitle } from './dialog';

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
        showCloseButton
        className="inset-0 left-0 top-0 flex h-dvh w-screen max-w-none translate-x-0 translate-y-0 flex-col overflow-hidden rounded-none border-0 bg-foreground p-4"
      >
        <DialogTitle className="sr-only">{title}</DialogTitle>
        {toolbar && <div className="flex min-h-12 shrink-0 items-center justify-center">{toolbar}</div>}
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <img
            src={src}
            alt={alt}
            className="max-h-full w-auto max-w-full object-contain"
            style={{ touchAction: 'auto' }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
