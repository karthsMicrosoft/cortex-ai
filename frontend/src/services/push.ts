import { apiDelete, apiGet, apiPost } from '../api/client';

export type PushStatus = 'unsupported' | 'denied' | 'unsubscribed' | 'subscribed' | 'unavailable';

interface VapidKeyResponse {
  public_key: string | null;
}

interface PushSubscribeResponse {
  id: string;
  created: boolean;
}

function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    typeof Notification !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window
  );
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = `${base64String}${padding}`.replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }

  return outputArray;
}

export async function getVapidPublicKey(): Promise<string | null> {
  const data = await apiGet<VapidKeyResponse>('/api/push/vapid-public-key');
  return data.public_key;
}

export async function getPushStatus(): Promise<PushStatus> {
  if (!isPushSupported()) return 'unsupported';
  if (Notification.permission === 'denied') return 'denied';

  const publicKey = await getVapidPublicKey().catch(() => null);
  if (publicKey === null) return 'unavailable';

  if (Notification.permission === 'default') return 'unsubscribed';

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  return subscription ? 'subscribed' : 'unsubscribed';
}

export async function requestPermission(): Promise<NotificationPermission> {
  if (typeof Notification === 'undefined') return 'denied';
  return Notification.requestPermission();
}

export async function subscribeToPush(): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null;

  const publicKey = await getVapidPublicKey();
  if (publicKey === null) return null;

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey) as unknown as BufferSource,
  });

  const subscriptionJson = subscription.toJSON();
  const endpoint = subscriptionJson.endpoint ?? subscription.endpoint;
  const keys = subscriptionJson.keys;

  if (!endpoint || !keys?.auth || !keys.p256dh) {
    throw new Error('Push subscription is missing required endpoint or keys.');
  }

  await apiPost<PushSubscribeResponse>('/api/push/subscribe', {
    endpoint,
    keys: {
      auth: keys.auth,
      p256dh: keys.p256dh,
    },
    user_agent: navigator.userAgent,
  });

  return subscription;
}

export async function unsubscribeFromPush(): Promise<boolean> {
  if (!isPushSupported()) return false;

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription) return false;

  await apiDelete('/api/push/subscribe', {
    body: { endpoint: subscription.endpoint },
  });
  await subscription.unsubscribe();
  return true;
}
