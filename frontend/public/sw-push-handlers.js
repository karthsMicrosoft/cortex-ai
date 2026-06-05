self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data?.json() ?? {};
  } catch {
    data = { title: event.data?.text() ?? 'Cortex', body: '' };
  }

  const { title = 'Cortex', body = '', url = '/', tag = undefined } = data;
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag,
      data: { url },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification.data?.url || '/';
  event.waitUntil((async () => {
    const allClients = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of allClients) {
      if ('focus' in client) {
        await client.navigate(targetUrl).catch(() => {});
        return client.focus();
      }
    }
    if (clients.openWindow) return clients.openWindow(targetUrl);
    return undefined;
  })());
});
