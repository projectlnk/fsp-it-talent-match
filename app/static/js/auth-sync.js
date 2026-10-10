// Cookies remain the source of truth. Messages contain only a random event ID.
document.addEventListener('DOMContentLoaded', () => {
  const key = 'fspcareer-auth';
  let channel;
  try { channel = new BroadcastChannel(key); } catch { /* storage fallback */ }
  const initial = new WeakMap();
  const snapshot = form => JSON.stringify(Array.from(form.elements)
    .filter(el => el.name && !el.disabled && !['hidden', 'submit', 'button'].includes(el.type))
    .map(el => [el.name, el.type === 'checkbox' || el.type === 'radio' ? el.checked :
      el.type === 'file' ? Array.from(el.files).map(f => [f.name, f.size, f.lastModified]) :
      el.tagName === 'SELECT' && el.multiple ? Array.from(el.selectedOptions).map(o => o.value) : el.value]));
  const remember = () => document.querySelectorAll('form').forEach(form => {
    if (!initial.has(form)) initial.set(form, snapshot(form));
  });
  remember();
  document.addEventListener('fspcareer:form-saved', event => {
    if (event.detail instanceof HTMLFormElement) initial.set(event.detail, snapshot(event.detail));
  });
  document.addEventListener('htmx:afterSwap', remember);
  const dirty = () => Array.from(document.forms).some(form =>
    initial.has(form) && initial.get(form) !== snapshot(form));
  const seen = new Set();
  const receive = id => {
    if (typeof id !== 'string' || !/^[a-f0-9]{32}$/.test(id) || seen.has(id)) return;
    seen.add(id);
    if (!dirty()) { location.reload(); return; }
    if (document.getElementById('auth-sync-notice')) return;
    const notice = document.createElement('div');
    notice.id = 'auth-sync-notice';
    notice.className = 'notice';
    notice.setAttribute('role', 'status');
    notice.append('Состояние входа изменилось в другой вкладке. Обновите страницу. ');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button button-small';
    button.textContent = 'Обновить';
    button.addEventListener('click', () => {
      if (!dirty() || confirm('Несохранённые изменения будут потеряны. Обновить страницу?')) location.reload();
    });
    notice.append(button);
    document.getElementById('main-content').prepend(notice);
  };
  if (channel) channel.onmessage = event => receive(event.data);
  window.addEventListener('storage', event => {
    if (event.key === key) receive(event.newValue);
  });
  // Issued only after successful cookie login/logout. Never a session credential.
  const signal = document.cookie.split('; ').find(value => value.startsWith('fspcareer_auth_change='));
  if (signal) {
    const id = signal.split('=')[1];
    document.cookie = 'fspcareer_auth_change=; Max-Age=0; Path=/; SameSite=Lax';
    seen.add(id);
    try { channel?.postMessage(id); } catch { /* storage fallback */ }
    try { localStorage.setItem(key, id); } catch { /* storage may be disabled */ }
  }
  // A restored browser-history page must not keep obsolete navigation.
  window.addEventListener('pageshow', event => { if (event.persisted) receive('0'.repeat(32)); });
});
