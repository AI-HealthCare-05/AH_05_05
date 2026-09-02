export interface ScheduledAlarm {
  id: number;
  alarmType: string;
  mealSlot: string | null;
  title: string;
  message: string | null;
  scheduledAt: string;
  recurrenceRule: string | null;
  status: string;
}
