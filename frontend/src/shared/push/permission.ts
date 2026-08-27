export type PushPermission = NotificationPermission | 'unsupported';

function isIosDevice(): boolean {
  return (
    /iPad|iPhone|iPod/i.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  );
}

function isStandaloneDisplay(): boolean {
  const standaloneNavigator = navigator as Navigator & { standalone?: boolean };
  return (
    standaloneNavigator.standalone === true ||
    window.matchMedia?.('(display-mode: standalone)').matches === true
  );
}

export function getPushPermission(): PushPermission {
  if (
    !('Notification' in window) ||
    !('serviceWorker' in navigator) ||
    (isIosDevice() && !isStandaloneDisplay())
  ) {
    return 'unsupported';
  }
  return window.Notification.permission;
}

export async function requestPushPermission(): Promise<PushPermission> {
  const current = getPushPermission();
  if (current !== 'default') return current;
  return window.Notification.requestPermission();
}
