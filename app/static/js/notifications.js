// Persistent unread state and an explicit, keyboard-accessible account switch.
document.addEventListener('DOMContentLoaded', () => {
  const badges = [...document.querySelectorAll('[data-message-badge]')];
  let busy = false;
  let denied = false;
  const refresh = async () => {
    if (!badges.length || busy || denied || document.hidden) return;
    busy = true;
    try {
      const response = await fetch('/career/message-notifications', {cache: 'no-store'});
      if ([401, 403].includes(response.status)) {
        denied = true;
        badges.forEach(badge => { badge.hidden = true; });
        return;
      }
      if (!response.ok) return;
      const data = await response.json();
      const count = Math.max(0, Math.floor(Number(data.count) || 0));
      badges.forEach(badge => {
        badge.hidden = count === 0;
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.setAttribute('aria-label', 'Новых сообщений: ' + count);
        badge.title = 'Новых сообщений: ' + count;
      });
    } catch { /* retain the last known value during a connection interruption */ }
    finally { busy = false; }
  };
  if (badges.length) {
    refresh();
    setInterval(refresh, 5000);
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('focus', refresh);
    window.addEventListener('pageshow', refresh);
    document.addEventListener('fspcareer:unread-changed', refresh);
  }

  const history = document.querySelector('[data-chat-read]');
  if (history) {
    let lastRead = 0;
    let reading = false;
    const markRead = async () => {
      const last = Number(history.dataset.lastMessage) || 0;
      if (document.hidden || reading || last <= lastRead) return;
      reading = true;
      try {
        const response = await fetch(history.dataset.chatRead, {
          method: 'POST',
          body: new URLSearchParams({token: history.dataset.chatToken, last_message: String(last)}),
          cache: 'no-store'
        });
        if (response.ok) {
          lastRead = Math.max(lastRead, Number((await response.json()).last_read) || 0);
          document.dispatchEvent(new CustomEvent('fspcareer:unread-changed'));
        }
      } catch { /* retry when the dialogue updates or regains visibility */ }
      finally { reading = false; }
    };
    markRead();
    document.addEventListener('fspcareer:chat-rendered', markRead);
    document.addEventListener('visibilitychange', markRead);
    window.addEventListener('focus', markRead);
  }

  const dialog = document.querySelector('[data-role-switch-dialog]');
  if (dialog && typeof dialog.showModal === 'function') {
    let trigger;
    document.querySelectorAll('[data-role-switch]').forEach(link => {
      link.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        trigger = link;
        dialog.showModal();
        dialog.querySelector('[data-role-switch-cancel]').focus();
      });
    });
    dialog.querySelector('[data-role-switch-cancel]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => trigger?.focus());
  }
});
