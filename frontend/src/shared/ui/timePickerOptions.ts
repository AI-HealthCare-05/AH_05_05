/** 시각은 30분 단위(분은 00 또는 30)만 허용합니다. */
export const MINUTE_OPTIONS = getMinuteOptions(30);

export type MinuteStep = 10 | 30;

export function getMinuteOptions(step: MinuteStep): string[] {
  return Array.from({ length: 60 / step }, (_, index) =>
    String(index * step).padStart(2, '0'),
  );
}

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) =>
  String(hour).padStart(2, '0'),
);
