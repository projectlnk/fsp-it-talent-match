// Only random signals and the current user ID are shared; never credentials.
document.addEventListener('DOMContentLoaded', () => {
  const key='fspcareer-auth';
  const refreshKey='fspcareer-session-refresh';
  try {
    if(sessionStorage.getItem(refreshKey)==='1'){
      sessionStorage.removeItem(refreshKey);
      location.replace('/auth/session-refresh');return;
    }
  } catch { /* browser storage can be disabled */ }
  const notice=document.getElementById('auth-sync-notice');
  if(!notice) return;
  const expected=Number(document.body.dataset.authUser || 0);
  let stale=false;
  const initial=new WeakMap();
  const snapshot=form=>JSON.stringify(Array.from(form.elements).filter(el=>el.name&&!el.disabled&&!['hidden','submit','button'].includes(el.type))
    .map(el=>[el.name,['checkbox','radio'].includes(el.type)?el.checked:el.type==='file'?Array.from(el.files).map(f=>[f.name,f.size,f.lastModified]):el.tagName==='SELECT'&&el.multiple?Array.from(el.selectedOptions).map(o=>o.value):el.value]));
  const remember=()=>document.querySelectorAll('form').forEach(form=>{if(!initial.has(form)) initial.set(form,snapshot(form));});
  remember();
  document.addEventListener('htmx:afterSwap',remember);
  document.addEventListener('fspcareer:form-saved',event=>{if(event.detail instanceof HTMLFormElement) initial.set(event.detail,snapshot(event.detail));});
  const dirty=()=>Array.from(document.forms).some(form=>initial.has(form)&&initial.get(form)!==snapshot(form));
  const show=()=>{
    if(stale) return;
    stale=true;
    try {sessionStorage.setItem(refreshKey,'1');} catch { /* server handles expired navigation too */ }
    notice.querySelector('[data-session-draft]').hidden=!dirty();
    document.querySelectorAll('dialog[open]').forEach(dialog=>{if(dialog!==notice) dialog.close();});
    notice.showModal();notice.querySelector('button').focus();
  };
  notice.addEventListener('cancel',event=>event.preventDefault());
  notice.querySelector('[data-session-refresh]').addEventListener('click',()=>{
    if(dirty()&&!confirm('Несохранённые изменения будут потеряны. Обновить страницу?')) return;
    try {sessionStorage.removeItem(refreshKey);} catch { /* no storage required */ }
    location.replace('/auth/session-refresh');
  });
  document.addEventListener('submit',event=>{if(stale){event.preventDefault();event.stopImmediatePropagation();}},true);
  document.addEventListener('htmx:beforeRequest',event=>{if(stale) event.preventDefault();});
  document.addEventListener('htmx:responseError',event=>{if(event.detail.xhr.status===401) show();});
  document.addEventListener('fspcareer:auth-invalid',show);
  // Includes native fetch feeds; API status codes and response bodies remain unchanged.
  const nativeFetch=window.fetch.bind(window);
  window.fetch=async (...args)=>{
    const response=await nativeFetch(...args);
    if(response.status===401 && new URL(response.url,location.href).origin===location.origin) show();
    return response;
  };
  let checking=false;
  const check=async()=>{
    if(checking||stale||document.hidden) return;
    checking=true;
    try {
      const response=await nativeFetch('/auth/session-state',{cache:'no-store'});
      if(response.ok && Number((await response.json()).user_id || 0)!==expected) show();
    } catch { /* a network outage does not mean logout */ }
    finally {checking=false;}
  };
  let channel;
  try {channel=new BroadcastChannel(key);channel.onmessage=()=>check();} catch { /* storage fallback */ }
  window.addEventListener('storage',event=>{if(event.key===key) check();});
  const signal=document.cookie.split('; ').find(value=>value.startsWith('fspcareer_auth_change='));
  if(signal){
    const id=signal.split('=')[1];
    document.cookie='fspcareer_auth_change=; Max-Age=0; Path=/; SameSite=Lax';
    try {channel?.postMessage(id);} catch { /* fallback below */ }
    try {localStorage.setItem(key,id);} catch { /* polling remains available */ }
  }
  window.addEventListener('pageshow',check);
  document.addEventListener('visibilitychange',check);
  window.addEventListener('focus',check);
  check();setInterval(check,10000);
});
