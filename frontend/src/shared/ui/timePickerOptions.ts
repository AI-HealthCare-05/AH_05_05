/** 시각은 30분 단위(분은 00 또는 30)만 허용합니다. */
export const MINUTE_OPTIONS = ['00', '30'];

export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) =>
  String(hour).padStart(2, '0'),
);
