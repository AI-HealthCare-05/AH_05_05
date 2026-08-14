import type { CSSProperties } from 'react';
import { Toaster as SonnerToaster, type ToasterProps } from 'sonner';

/**
 * shadcn/ui Sonner(Toast) — 수기 작성.
 * shadcn 기본 코드는 next-themes로 다크모드를 반영하지만 이 앱은 다크모드가
 * 없어(계약서에 다크 토큰 없음) 라이트 테마로 고정했습니다.
 * 색은 이 프로젝트의 CSS 변수를 그대로 참조합니다(sonner가 요구하는
 * --normal-bg 등의 이름에 우리 값을 연결).
 */
export function Toaster(props: ToasterProps) {
  return (
    <SonnerToaster
      theme="light"
      className="toaster group"
      style={
        {
          '--normal-bg': 'var(--color-popover)',
          '--normal-text': 'var(--color-popover-foreground)',
          '--normal-border': 'var(--color-border)',
          '--success-bg': 'var(--color-success-bg)',
          '--success-text': 'var(--color-success-strong)',
          '--success-border': 'var(--color-success)',
          '--error-bg': 'var(--color-danger-bg)',
          '--error-text': 'var(--color-danger-strong)',
          '--error-border': 'var(--color-danger)',
          '--warning-bg': 'var(--color-warning-bg)',
          '--warning-text': 'var(--color-warning-strong)',
          '--warning-border': 'var(--color-warning)',
        } as CSSProperties
      }
      toastOptions={{
        classNames: {
          title: 'text-sm font-bold',
          description: 'text-sm',
        },
      }}
      {...props}
    />
  );
}
