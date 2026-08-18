self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let p = {};
  if (event.data) {
    // 서버는 JSON을 보내지만 DevTools Push 버튼은 문자열을 그대로 보냅니다. 둘 다 받습니다.
    try { p = event.data.json(); } catch { p = { title: '포케', body: event.data.text() }; }
  }
  event.waitUntil(
    self.registration.showNotification(p.title || '포케', {
      body: p.body || '',
      tag: p.tag || 'poke-test',
      data: { url: p.url || '/' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) if ('focus' in c) { c.navigate(url); return c.focus(); }
      return self.clients.openWindow(url);
    }),
  );
});
