self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { body: event.data?.text() ?? '' };
  }

  const title = typeof payload.title === 'string' ? payload.title : '포케';
  const options = {
    body: typeof payload.body === 'string' ? payload.body : '',
    data: {
      url: typeof payload.url === 'string' ? payload.url : '/home',
      ...(payload.data && typeof payload.data === 'object' ? payload.data : {}),
    },
    tag: typeof payload.tag === 'string' ? payload.tag : undefined,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url ?? '/home';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (clients) => {
      for (const client of clients) {
        if ('navigate' in client) await client.navigate(targetUrl);
        return client.focus();
      }
      return self.clients.openWindow(targetUrl);
    }),
  );
});
