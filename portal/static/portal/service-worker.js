const CACHE='sarkarinaukri-v3';
const APP_SHELL=['/','/jobs/','/exam-calendar/','/static/portal/styles.css','/static/portal/app.js','/static/portal/icon-192.png','/static/portal/icon-512.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(APP_SHELL).catch(()=>{})));self.skipWaiting();});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET')return;
  const url=new URL(event.request.url);
  if(url.origin!==location.origin)return;
  event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();if(response.ok && !url.pathname.startsWith('/admin/') && !url.pathname.startsWith('/account/') && !url.pathname.startsWith('/accounts/') && !url.pathname.startsWith('/staff-2fa/') && !url.pathname.startsWith('/ops/') && !url.pathname.startsWith('/analytics/'))caches.open(CACHE).then(c=>c.put(event.request,copy));return response;}).catch(()=>caches.match(event.request).then(r=>r||caches.match('/'))));
});
self.addEventListener('push',event=>{let data={title:'SarkariNaukri update',body:'A government-job update is available.',url:'/'};try{data={...data,...event.data.json()};}catch(e){}event.waitUntil(self.registration.showNotification(data.title,{body:data.body,icon:'/static/portal/icon-192.png',badge:'/static/portal/icon-192.png',data:{url:data.url},tag:data.url}));});
self.addEventListener('notificationclick',event=>{event.notification.close();const url=(event.notification.data&&event.notification.data.url)||'/';event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{for(const c of list){if(c.url===url&&'focus'in c)return c.focus();}return clients.openWindow(url);}));});
