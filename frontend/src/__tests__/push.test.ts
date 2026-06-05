import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({
      accessToken: 'test-token',
      logout: vi.fn(),
      setAccessToken: vi.fn(),
    })),
  },
}));

import { getPushStatus, subscribeToPush, unsubscribeFromPush } from '../services/push';

const fetchMock = vi.fn();
const originalServiceWorker = Object.getOwnPropertyDescriptor(navigator, 'serviceWorker');
const originalPushManager = Object.getOwnPropertyDescriptor(window, 'PushManager');
const originalNotification = Object.getOwnPropertyDescriptor(globalThis, 'Notification');

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    headers: { get: () => null },
    json: async () => body,
  } as unknown as Response;
}

function mockFetchResponses(...responses: Response[]): void {
  fetchMock.mockReset();
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response);
  }
  vi.stubGlobal('fetch', fetchMock);
}

function setNotificationPermission(permission: NotificationPermission): void {
  const notification = {
    requestPermission: vi.fn().mockResolvedValue(permission),
  };
  Object.defineProperty(notification, 'permission', {
    configurable: true,
    value: permission,
  });
  vi.stubGlobal('Notification', notification as unknown as typeof Notification);
}

function setPushManagerSupport(supported = true): void {
  if (supported) {
    Object.defineProperty(window, 'PushManager', {
      configurable: true,
      value: vi.fn(),
    });
  } else {
    Reflect.deleteProperty(window, 'PushManager');
  }
}

function makeSubscription() {
  return {
    endpoint: 'https://push.example/subscription/1',
    toJSON: () => ({
      endpoint: 'https://push.example/subscription/1',
      keys: {
        auth: 'auth-token',
        p256dh: 'p256dh-token',
      },
    }),
    unsubscribe: vi.fn().mockResolvedValue(true),
  } as unknown as PushSubscription & { unsubscribe: ReturnType<typeof vi.fn> };
}

function setServiceWorker(subscription: PushSubscription | null = null) {
  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(subscription),
    subscribe: vi.fn().mockResolvedValue(makeSubscription()),
  };
  const registration = { pushManager } as unknown as ServiceWorkerRegistration;
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: { ready: Promise.resolve(registration) },
  });
  return { pushManager, registration };
}

function removeServiceWorker(): void {
  Reflect.deleteProperty(navigator, 'serviceWorker');
}

beforeEach(() => {
  vi.clearAllMocks();
  setPushManagerSupport(true);
  setNotificationPermission('default');
  setServiceWorker(null);
  mockFetchResponses(jsonResponse(200, { public_key: 'AQIDBA' }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  if (originalServiceWorker) Object.defineProperty(navigator, 'serviceWorker', originalServiceWorker);
  else Reflect.deleteProperty(navigator, 'serviceWorker');
  if (originalPushManager) Object.defineProperty(window, 'PushManager', originalPushManager);
  else Reflect.deleteProperty(window, 'PushManager');
  if (originalNotification) Object.defineProperty(globalThis, 'Notification', originalNotification);
  else Reflect.deleteProperty(globalThis, 'Notification');
});

describe('getPushStatus', () => {
  it('returns unsupported when service workers are unavailable', async () => {
    removeServiceWorker();
    await expect(getPushStatus()).resolves.toBe('unsupported');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns denied when notification permission is denied', async () => {
    setNotificationPermission('denied');
    await expect(getPushStatus()).resolves.toBe('denied');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns unsubscribed when permission is default and VAPID is configured', async () => {
    setNotificationPermission('default');
    await expect(getPushStatus()).resolves.toBe('unsubscribed');
  });

  it('returns subscribed when an existing subscription is present', async () => {
    setNotificationPermission('granted');
    setServiceWorker(makeSubscription());
    await expect(getPushStatus()).resolves.toBe('subscribed');
  });

  it('returns unavailable when the backend has no VAPID key', async () => {
    mockFetchResponses(jsonResponse(200, { public_key: null }));
    await expect(getPushStatus()).resolves.toBe('unavailable');
  });
});

describe('subscribeToPush', () => {
  it('subscribes with the VAPID key and POSTs endpoint, keys, and user agent', async () => {
    setNotificationPermission('granted');
    const subscription = makeSubscription();
    const { pushManager } = setServiceWorker(null);
    pushManager.subscribe.mockResolvedValueOnce(subscription);
    mockFetchResponses(
      jsonResponse(200, { public_key: 'AQIDBA' }),
      jsonResponse(200, { id: 'sub-1', created: true }),
    );

    const result = await subscribeToPush();

    expect(result).toBe(subscription);
    expect(pushManager.subscribe).toHaveBeenCalledWith({
      userVisibleOnly: true,
      applicationServerKey: expect.any(Uint8Array),
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/push/subscribe');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      endpoint: 'https://push.example/subscription/1',
      keys: { auth: 'auth-token', p256dh: 'p256dh-token' },
      user_agent: navigator.userAgent,
    });
  });

  it('returns null without subscribing when the VAPID key is unavailable', async () => {
    const { pushManager } = setServiceWorker(null);
    mockFetchResponses(jsonResponse(200, { public_key: null }));

    await expect(subscribeToPush()).resolves.toBeNull();
    expect(pushManager.subscribe).not.toHaveBeenCalled();
  });
});

describe('unsubscribeFromPush', () => {
  it('DELETEs the backend subscription and unsubscribes the browser subscription', async () => {
    const subscription = makeSubscription();
    setServiceWorker(subscription);
    mockFetchResponses(jsonResponse(204, null));

    await expect(unsubscribeFromPush()).resolves.toBe(true);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/push/subscribe');
    expect(init.method).toBe('DELETE');
    expect(JSON.parse(init.body as string)).toEqual({ endpoint: subscription.endpoint });
    expect(subscription.unsubscribe).toHaveBeenCalledTimes(1);
  });
});
