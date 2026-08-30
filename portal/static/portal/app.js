(function(){
  const root=document.documentElement;
  const savedTheme=localStorage.getItem('sn-theme');
  if(savedTheme){ root.dataset.theme=savedTheme; }
  else if(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches){ root.dataset.theme='dark'; }

  const themeBtn=document.getElementById('theme-toggle');
  if(themeBtn){ themeBtn.addEventListener('click',()=>{ const next=root.dataset.theme==='dark'?'light':'dark'; root.dataset.theme=next; localStorage.setItem('sn-theme',next); }); }

  const mobileBtn=document.getElementById('mobile-toggle');
  const mobileMenu=document.getElementById('mobile-menu');
  if(mobileBtn && mobileMenu){ mobileBtn.addEventListener('click',()=>{ const open=mobileMenu.hasAttribute('hidden'); if(open){mobileMenu.removeAttribute('hidden');}else{mobileMenu.setAttribute('hidden','');} mobileBtn.setAttribute('aria-expanded',String(open)); }); }

  if('serviceWorker' in navigator){ window.addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js').catch(()=>{})); }
  let deferredPrompt=null;
  const installBtn=document.getElementById('install-app');
  window.addEventListener('beforeinstallprompt',(e)=>{ e.preventDefault(); deferredPrompt=e; if(installBtn) installBtn.hidden=false; });
  if(installBtn){ installBtn.addEventListener('click',async()=>{ if(!deferredPrompt)return; deferredPrompt.prompt(); await deferredPrompt.userChoice; deferredPrompt=null; installBtn.hidden=true; }); }

  function debounce(fn, wait){ let timer; return function(...args){clearTimeout(timer);timer=setTimeout(()=>fn.apply(this,args),wait);} }
  document.querySelectorAll('[data-autocomplete]').forEach(input=>{
    const wrap=input.closest('.autocomplete-wrap'); const list=wrap?wrap.querySelector('[data-autocomplete-list]'):null;
    if(!list)return;
    const run=debounce(async()=>{
      const q=input.value.trim(); if(q.length<2){list.hidden=true;list.innerHTML='';return;}
      try{ const r=await fetch(`${window.SN_CONFIG.autocomplete}?q=${encodeURIComponent(q)}`,{headers:{'Accept':'application/json'}}); const data=await r.json();
        list.innerHTML=(data.results||[]).map(x=>`<a class="autocomplete-item" href="${x.url}"><strong>${escapeHtml(x.label)}</strong><small>${escapeHtml(x.sub||'')}</small></a>`).join('');
        list.hidden=!data.results||data.results.length===0;
      }catch(e){ list.hidden=true; }
    },220);
    input.addEventListener('input',run);
    input.addEventListener('keydown',e=>{ if(e.key==='Escape')list.hidden=true; });
    document.addEventListener('click',e=>{ if(!wrap.contains(e.target))list.hidden=true; });
  });

  function escapeHtml(v){return String(v||'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[c]));}
  function getCookie(name){const bits=document.cookie.split(';').map(v=>v.trim());for(const part of bits){if(part.startsWith(name+'='))return decodeURIComponent(part.slice(name.length+1));}return '';}
  function urlBase64ToUint8Array(base64String){const padding='='.repeat((4-base64String.length%4)%4);const base64=(base64String+padding).replace(/-/g,'+').replace(/_/g,'/');const raw=window.atob(base64);return Uint8Array.from([...raw].map(c=>c.charCodeAt(0)));}

  document.querySelectorAll('.push-enable').forEach(btn=>btn.addEventListener('click',async()=>{
    if(!window.SN_CONFIG.authenticated){window.location.href='/accounts/login/?next='+encodeURIComponent(location.pathname);return;}
    if(!('serviceWorker' in navigator) || !('PushManager' in window) || !window.SN_CONFIG.vapidPublicKey){alert('Browser push is not configured for this deployment.');return;}
    try{
      const permission=await Notification.requestPermission(); if(permission!=='granted')return;
      const reg=await navigator.serviceWorker.ready;
      let sub=await reg.pushManager.getSubscription();
      if(!sub){sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlBase64ToUint8Array(window.SN_CONFIG.vapidPublicKey)});}
      const r=await fetch(window.SN_CONFIG.pushSubscribe,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')},body:JSON.stringify(sub.toJSON())});
      if(!r.ok)throw new Error('Subscription save failed');
      btn.textContent='Browser alerts enabled ✓'; btn.disabled=true;
    }catch(e){alert('Could not enable browser alerts. Check notification permissions and VAPID configuration.');}
  }));
})();
