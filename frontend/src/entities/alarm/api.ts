import { http, mockDelay } from '@/shared/api/client';
import { USE_MOCK } from '@/shared/config/env';
import { mockGetActiveScheduledAlarms } from './api.mock';
import type { ScheduledAlarm } from './types';

interface AlarmApiResponse {
  id: number;
  user_id: number;
  care_episode_id: number | null;
  source_guide_id: number | null;
  follow_up_visit_id: number | null;
  alarm_type: string;
  meal_slot: string | null;
  title: string;
  message: string | null;
  scheduled_at: string;
  recurrence_rule: string | null;
  status: string;
}

interface AlarmListApiResponse {
  items: AlarmApiResponse[];
  total: number;
  offset: number;
  limit: number;
}

function mapScheduledAlarm(response: AlarmApiResponse): ScheduledAlarm {
  return {
    id: response.id,
    alarmType: response.alarm_type,
    mealSlot: response.meal_slot,
    title: response.title,
    message: response.message,
    scheduledAt: response.scheduled_at,
    recurrenceRule: response.recurrence_rule,
    status: response.status,
  };
}

function compareScheduledAlarms(left: ScheduledAlarm, right: ScheduledAlarm): number {
  return left.scheduledAt.localeCompare(right.scheduledAt) || left.id - right.id;
}

export async function getActiveScheduledAlarms(): Promise<ScheduledAlarm[]> {
  if (USE_MOCK) {
    await mockDelay();
    return mockGetActiveScheduledAlarms().sort(compareScheduledAlarms);
  }
  const response = await http.get<AlarmListApiResponse>(
    '/v1/alarms?status=ACTIVE&offset=0&limit=100',
  );
  return response.items.map(mapScheduledAlarm).sort(compareScheduledAlarms);
}
