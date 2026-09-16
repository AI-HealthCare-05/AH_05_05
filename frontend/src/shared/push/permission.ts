export type PushPermission = NotificationPermission | 'ios-install-required' | 'unsupported';

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
    !('serviceWorker' in navigator)
  ) {
    return 'unsupported';
  }
  if (isIosDevice() && !isStandaloneDisplay()) return 'ios-install-required';
  return window.Notification.permission;
}

export async function requestPushPermission(): Promise<PushPermission> {
  const current = getPushPermission();
  if (current !== 'default') return current;
  return window.Notification.requestPermission();
}
