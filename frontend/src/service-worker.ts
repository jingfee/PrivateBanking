/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />
import { build, files, version } from '$service-worker';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `shell-${version}`;
const SHELL = [...build, ...files, '/'];

sw.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => sw.skipWaiting()));
});

sw.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => sw.clients.claim())
  );
});

// App shell only: API and the bank callback always go to the network.
sw.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/callback')) return;
  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      if (SHELL.includes(url.pathname)) return (await cache.match(url.pathname)) ?? fetch(event.request);
      try {
        return await fetch(event.request);
      } catch {
        return (await cache.match('/')) ?? Response.error();
      }
    })()
  );
});
