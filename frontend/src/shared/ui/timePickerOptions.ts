/** 복약 알림 시각은 1분 단위(00~59분)로 선택합니다. */
export const MINUTE_OPTIONS = getMinuteOptions(1);

export type MinuteStep = 1 | 10 | 30;

export function getMinuteOptions(step: MinuteStep): string[] {
  return Array.from({ length: 60 / step }, (_, index) =>
    String(index * step).padStart(2, '0'),
  );
}

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) =>
  String(hour).padStart(2, '0'),
);
