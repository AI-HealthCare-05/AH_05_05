export interface NotifySettings {
  notifyMedication: boolean;
  notifySupplement: boolean;
  notifyConsentedAt: string | null;
}

export type NotifySettingKey = 'notifyMedication' | 'notifySupplement';

export type UpdateNotifySettingsPayload = Partial<
  Pick<NotifySettings, 'notifyMedication' | 'notifySupplement'>
>;
