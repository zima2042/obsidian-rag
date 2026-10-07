/* Obsidian 知识库 PWA Service Worker — 只缓存静态资源，API 不缓存 */
const CACHE = 'kb-v14';
const ASSETS = ['./', './index.html', './style.css?v=13', './app.js', './manifest.webmanifest', './icon-192.png', './icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))   /* 清空全部旧缓存（含旧版本号） */
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  /* API 请求一律直连，不缓存 */
  const p = url.pathname;
  if (p.startsWith('/ask') || p.startsWith('/stats') || p.startsWith('/search') ||
      p.startsWith('/note') || p.startsWith('/health')) return;
  e.respondWith(
    fetch(req).then(res => {
      /* 只缓存成功的 200 响应；304（资源未变）直接原样放行，
         让浏览器用自己 HTTP 缓存里的最新版本——绝不让 304 掉进下面的兜底缓存 */
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
      }
      return res;
    }).catch(() => caches.match(req).then(m => m || caches.match('./')))
  );
});
