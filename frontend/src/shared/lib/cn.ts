import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export type { ClassValue };

/**
 * shadcn/ui 표준 cn 유틸(clsx + tailwind-merge).
 * 호출 형태 cn(...args)는 기존과 동일하므로 사용처는 바꿀 필요가 없습니다.
 *
 * 참고: tailwind-merge는 기본 설정으로는 이 프로젝트가 @theme에 추가한
 * 커스텀 클래스(rounded-card, bg-warning-bg, h-touch 등)를 같은 그룹으로
 * 인식하지 못합니다. 즉 서로 충돌하는 커스텀 클래스를 함께 넘겨도 자동으로
 * 병합(마지막 값 우선)해주지 않을 수 있습니다. 지금까지 컴포넌트들은 그런
 * 충돌 패턴으로 쓰이지 않아 문제가 없었지만, 커스텀 토큰 클래스를 className
 * prop으로 덮어쓰는 경우가 늘면 tailwind-merge를 extendTailwindMerge로
 * 확장하는 것을 검토하세요.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
