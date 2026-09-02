export interface MedicationTimes {
  morningMedicationTime: string;
  lunchMedicationTime: string;
  eveningMedicationTime: string;
  bedtimeMedicationTime: string;
}

export interface NotifySettings extends MedicationTimes {
  notifyMedication: boolean;
  notifySupplement: boolean;
  notifyConsentedAt: string | null;
}

export type NotifySettingKey = 'notifyMedication' | 'notifySupplement';

export type UpdateNotifySettingsPayload = Partial<
  Pick<
    NotifySettings,
    | 'notifyMedication'
    | 'notifySupplement'
    | 'morningMedicationTime'
    | 'lunchMedicationTime'
    | 'eveningMedicationTime'
    | 'bedtimeMedicationTime'
  >
>;
