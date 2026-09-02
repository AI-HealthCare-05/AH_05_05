export interface MedicationTimes {
  morningMedicationTime: string;
  lunchMedicationTime: string;
  eveningMedicationTime: string;
  bedtimeMedicationTime: string;
}

export interface NotifySettings extends MedicationTimes {
  notifyMedication: boolean;
  notifySupplement: boolean;
  notifySchedule: boolean;
  notifyConsentedAt: string | null;
}

export type NotifySettingKey = 'notifyMedication' | 'notifySupplement' | 'notifySchedule';

export type UpdateNotifySettingsPayload = Partial<
  Pick<
    NotifySettings,
    | 'notifyMedication'
    | 'notifySupplement'
    | 'notifySchedule'
    | 'morningMedicationTime'
    | 'lunchMedicationTime'
    | 'eveningMedicationTime'
    | 'bedtimeMedicationTime'
  >
>;
