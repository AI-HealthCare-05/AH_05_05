import { Dialog, DialogContent, DialogTitle } from './dialog';

export interface ImageViewerProps {
  open: boolean;
  src: string;
  title: string;
  onOpenChange: (open: boolean) => void;
}

/**
 * 등록 문서 원본을 화면 가득 확인하는 뷰어입니다.
 * 이미지의 기본 확대 제스처를 막지 않도록 touch-action을 auto로 유지합니다.
 */
export function ImageViewer({ open, src, title, onOpenChange }: ImageViewerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton
        className="inset-0 left-0 top-0 h-dvh w-screen max-w-none translate-x-0 translate-y-0 place-items-center overflow-auto rounded-none border-0 bg-foreground p-4"
      >
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <img
          src={src}
          alt="확대한 약봉투 원본"
          className="max-h-full w-auto max-w-full object-contain"
          style={{ touchAction: 'auto' }}
        />
      </DialogContent>
    </Dialog>
  );
}
