import { http } from '@/shared/api/client';
import { VAPID_PUBLIC_KEY } from '@/shared/config/env';
import { getPushPermission } from './permission';

function decodeVapidPublicKey(value: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/');
  const bytes = Uint8Array.from(window.atob(base64), (character) => character.charCodeAt(0));
  return new Uint8Array(bytes.buffer);
}

function platformFromUserAgent(userAgent: string): string {
  if (/android/i.test(userAgent)) return 'android';
  if (/iPad|iPhone|iPod/i.test(userAgent)) return 'ios';
  return 'web';
}

export async function registerPushNotifications(
  vapidPublicKey: string = VAPID_PUBLIC_KEY,
): Promise<void> {
  if (getPushPermission() !== 'granted') {
    throw new Error('알림 권한을 허용한 뒤 다시 시도해주세요.');
  }
  if (!vapidPublicKey) {
    throw new Error('알림 공개키가 설정되지 않았어요.');
  }

  const registration = await navigator.serviceWorker.register('/sw.js');
  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodeVapidPublicKey(vapidPublicKey),
    }));
  const json = subscription.toJSON();
  const endpoint = json.endpoint;
  const p256dhKey = json.keys?.p256dh;
  const authKey = json.keys?.auth;
  if (!endpoint || !p256dhKey || !authKey) {
    throw new Error('알림 구독 정보를 만들지 못했어요.');
  }

  await http.put('/v1/alarms/push-subscriptions', {
    endpoint,
    p256dh_key: p256dhKey,
    auth_key: authKey,
    platform: platformFromUserAgent(navigator.userAgent),
    user_agent: navigator.userAgent,
  });
}
