import { http, restoreAccountPrincipal } from '@/shared/api/client';
import { USE_MOCK, VAPID_PUBLIC_KEY } from '@/shared/config/env';
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

const PUSH_REGISTRATION_STORAGE_KEY = 'poke.push-subscription-registration';

interface StoredPushRegistration {
  principalKey: string;
  subscriptionIds: number[];
}

function readStoredPushRegistration(): StoredPushRegistration | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(PUSH_REGISTRATION_STORAGE_KEY) ?? 'null') as {
      principalKey?: unknown;
      subscriptionId?: unknown;
      subscriptionIds?: unknown;
    } | null;
    if (!parsed || typeof parsed.principalKey !== 'string') return null;
    const candidateIds = Array.isArray(parsed.subscriptionIds)
      ? parsed.subscriptionIds
      : [parsed.subscriptionId];
    const subscriptionIds = candidateIds.filter(
      (value): value is number => typeof value === 'number' && Number.isInteger(value) && value > 0,
    );
    return { principalKey: parsed.principalKey, subscriptionIds };
  } catch {
    return null;
  }
}

function storePushRegistration(registration: StoredPushRegistration): void {
  try {
    localStorage.setItem(PUSH_REGISTRATION_STORAGE_KEY, JSON.stringify(registration));
  } catch {
    // 브라우저 저장소가 차단되어도 Push 등록 자체는 유지합니다.
  }
}

let registrationInFlight: Promise<void> | null = null;

async function performPushRegistration(vapidPublicKey: string): Promise<void> {
  if (getPushPermission() !== 'granted') {
    throw new Error('알림 권한을 허용한 뒤 다시 시도해주세요.');
  }
  if (!vapidPublicKey) {
    // 목업 화면 검증에서는 실 Push 서버나 공개키가 없어도 설정 저장 흐름을 이어갑니다.
    if (USE_MOCK) return;
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

  const registered = await http.put<{ id: number }>('/v1/alarms/push-subscriptions', {
    endpoint,
    p256dh_key: p256dhKey,
    auth_key: authKey,
    platform: platformFromUserAgent(navigator.userAgent),
    user_agent: navigator.userAgent,
  });

  const principalKey = restoreAccountPrincipal()?.trim().toLowerCase();
  if (!principalKey || !Number.isInteger(registered.id) || registered.id <= 0) return;

  const previous = readStoredPushRegistration();
  const staleIds = previous?.principalKey === principalKey
    ? previous.subscriptionIds.filter((id) => id !== registered.id)
    : [];
  const cleanupResults = await Promise.allSettled(
    staleIds.map((id) => http.delete(`/v1/alarms/push-subscriptions/${id}`)),
  );
  const failedStaleIds = staleIds.filter((_, index) => cleanupResults[index]?.status === 'rejected');
  storePushRegistration({
    principalKey,
    subscriptionIds: [registered.id, ...failedStaleIds],
  });
}

/**
 * StrictMode의 effect 재실행이나 여러 화면의 동시 요청은 같은 등록 작업을 공유합니다.
 * 완료 또는 실패 뒤에는 잠금을 해제하여 이후 재등록 시도를 허용합니다.
 */
export function registerPushNotifications(
  vapidPublicKey: string = VAPID_PUBLIC_KEY,
): Promise<void> {
  if (registrationInFlight) return registrationInFlight;

  const registration = performPushRegistration(vapidPublicKey).finally(() => {
    if (registrationInFlight === registration) registrationInFlight = null;
  });
  registrationInFlight = registration;
  return registration;
}

interface PushSubscriptionListResponse {
  items: Array<{ id: number; endpoint: string }>;
}

interface UnregisterPushNotificationsOptions {
  deactivateServer?: boolean;
}

/**
 * 현재 브라우저의 Push endpoint를 더 이상 사용할 수 없게 정리합니다.
 * 명시적 로그아웃에서는 토큰이 유효한 동안 서버 행부터 비활성화하고,
 * 세션 만료에서는 인증 API를 다시 호출하지 않고 브라우저 구독만 해제합니다.
 */
export async function unregisterPushNotifications(
  { deactivateServer = true }: UnregisterPushNotificationsOptions = {},
): Promise<void> {
  if (!('serviceWorker' in navigator)) return;
  const getRegistration = navigator.serviceWorker.getRegistration;
  if (typeof getRegistration !== 'function') return;

  let subscription: PushSubscription | null = null;
  try {
    const registration = await getRegistration.call(navigator.serviceWorker);
    subscription = (await registration?.pushManager.getSubscription()) ?? null;
    if (!subscription) return;
    if (deactivateServer) {
      const endpoint = subscription.endpoint;
      const response = await http.get<PushSubscriptionListResponse>('/v1/alarms/push-subscriptions');
      const registered = response.items.find((item) => item.endpoint === endpoint);
      if (registered) {
        await http.delete(`/v1/alarms/push-subscriptions/${registered.id}`);
      }
    }
  } catch {
    // 로그아웃을 서버의 구독 정리 실패로 막지 않습니다. 브라우저 구독은 항상 해제합니다.
  } finally {
    if (subscription) {
      try {
        await subscription.unsubscribe();
      } catch {
        // 브라우저 자체 해제 실패도 인증 종료를 막아서는 안 됩니다.
      }
    }
  }
}
