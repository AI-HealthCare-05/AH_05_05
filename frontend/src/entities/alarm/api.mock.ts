import type { ScheduledAlarm } from './types';

const alarms: ScheduledAlarm[] = [
  {
    id: 1,
    alarmType: 'FOLLOW_UP_VISIT',
    mealSlot: null,
    title: '진료일정 알림',
    message: '늘봄병원 진료가 예정되어 있어요.',
    scheduledAt: '2026-09-05T10:00:00+09:00',
    recurrenceRule: null,
    status: 'ACTIVE',
  },
  {
    id: 2,
    alarmType: 'MEDICATION',
    mealSlot: 'MORNING',
    title: '아침 복약 알림',
    message: '약을 복용할 시간입니다.',
    scheduledAt: '2026-09-03T08:00:00+09:00',
    recurrenceRule: 'FREQ=DAILY;COUNT=7',
    status: 'ACTIVE',
  },
];

export function mockGetActiveScheduledAlarms(): ScheduledAlarm[] {
  return alarms.map((alarm) => ({ ...alarm }));
}
