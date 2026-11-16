/* Preview-only kill switch. Not used on the live site.
   Frees a phone stuck on an old cached copy of /emmavengers-world-preview/:
   take over at once, delete only this path's caches, unregister, and send
   open tabs to the fresh test URL (a new path, so no old worker applies).
   Live-site caches and the shared bible cache are left alone. */
const NEW_URL = 'https://emmavengerskidsworld-design.github.io/emmavengers-world-test/';
const PFX = 'emma-house-/emmavengers-world-preview/-';

self.addEventListener('install', e => {
  e.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) {
      if (k.startsWith(PFX) || k.includes('/emmavengers-world-preview/')) {
        await caches.delete(k);
      }
    }
    await self.registration.unregister();
    const cl = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
    await self.clients.claim();
    /* Do not await navigate() inside waitUntil: that can deadlock. */
    setTimeout(() => {
      cl.forEach(c => {
        try {
          if (c.navigate) c.navigate(NEW_URL);
        } catch (err) {}
      });
    }, 50);
  })());
});
