document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll('[data-loading-form]').forEach(form => form.addEventListener('submit', () => {
    form.setAttribute('aria-busy', 'true');
    const loadingStatus=form.querySelector('[data-submit-status], [data-loading-status]');
    if(loadingStatus) loadingStatus.hidden = false;
    form.querySelector('button[type="submit"]').disabled = true;
  }));
  const status = document.getElementById("js-status");
  if (status) status.textContent = "JavaScript работает";
  const visibilityForm = document.querySelector('#visibility .visibility-form');
  if (visibilityForm) {
    const checkbox = visibilityForm.querySelector('[name="published"]');
    const message = document.querySelector('[data-visibility-status]');
    checkbox.addEventListener('change', async () => {
      const value = checkbox.checked;
      const payload = new FormData(visibilityForm);
      checkbox.disabled = true;
      message.textContent = 'Сохраняется…';
      try {
        const response = await fetch(visibilityForm.action, {method: 'POST', body: payload});
        if (!response.ok || new URL(response.url).searchParams.get('saved') !== '1') throw new Error('Save failed');
        checkbox.disabled = false;
        document.dispatchEvent(new CustomEvent('fspcareer:form-saved', {detail: visibilityForm}));
        message.textContent = 'Сохранено';
        const indicator = document.querySelector('[data-profile-visibility-indicator]');
        if (indicator) indicator.textContent = value ? 'Профиль доступен работодателям при подтверждённой категории' : 'Профиль скрыт от работодателей';
      } catch {
        checkbox.checked = !value;
        message.textContent = 'Не удалось сохранить. Обновите страницу и повторите.';
      } finally {
        checkbox.disabled = false;
      }
    });
  }
  const resumeDialog = document.querySelector('[data-resume-dialog]');
  const resumeOpen = document.querySelector('[data-resume-open]');
  if (resumeDialog && resumeOpen) {
    let resumeTrigger = resumeOpen;
    document.querySelectorAll('[data-resume-open]').forEach(trigger => {
      trigger.addEventListener('click', event => {
        event.preventDefault();
        resumeTrigger = trigger;
        resumeDialog.showModal();
      });
    });
    resumeDialog.querySelector('[data-resume-cancel]').addEventListener('click', () => resumeDialog.close());
    resumeDialog.querySelector('[data-resume-confirm]').addEventListener('click', () => resumeDialog.close());
    resumeDialog.addEventListener('close', () => resumeTrigger.focus());
  }
  // Prototype interactions are intentionally scoped to /design-preview.
  if (!/^\/design-preview(?:\/|$)/.test(location.pathname)) return;
  const key = "fsp-design-preview:";
  const read = (name, fallback = null) => { try { return JSON.parse(sessionStorage.getItem(key + name)) ?? fallback; } catch { return fallback; } };
  const write = (name, value) => { try { sessionStorage.setItem(key + name, JSON.stringify(value)); } catch { /* Storage can be disabled; the visual demo still works. */ } };
  let toastTimer;
  const notify = (message) => { const toast = document.getElementById("toast"); toast.textContent = message; toast.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.hidden = true; }, 5500); };
  const privacy = () => read("privacy", {visible: true, invites: true, achievements: true, contacts: true});
  const applyContacts = () => document.querySelectorAll("[data-contact-panel]").forEach(panel => {
    const open = read("invitation:" + panel.dataset.contactPanel) === "accepted" && privacy().contacts;
    panel.querySelector("[data-contact-open]").hidden = !open;
    panel.querySelector("[data-contact-locked]").hidden = open;
  });
  applyContacts();
  const search = document.getElementById("demo-search");
  if (search) {
    const apply = () => {
      const values = new FormData(search); let count = 0;
      const query = String(values.get("query") || "").trim().toLocaleLowerCase("ru");
      document.querySelectorAll("[data-candidate-card]").forEach(card => {
        const matches = (!query || card.dataset.search.toLocaleLowerCase("ru").includes(query)) && ["specialization", "grade", "format"].every(name => !values.get(name) || card.dataset[name] === values.get(name)) && (!values.get("fsp") || card.dataset.fsp === "yes");
        card.hidden = !matches; if (matches) count++;
      });
      document.getElementById("result-count").textContent = "Найдено: " + count;
      document.getElementById("search-empty").hidden = count !== 0;
    };
    search.addEventListener("submit", event => { event.preventDefault(); apply(); });
    search.addEventListener("reset", () => setTimeout(apply, 0));
    document.querySelector("[data-reset-search]").addEventListener("click", () => search.reset());
  }
  const inviteActions = document.querySelector("[data-invitation-actions]");
  if (inviteActions) {
    const id = inviteActions.dataset.invitationActions;
    const update = () => {
      const state = read("invitation:" + id, "sent");
      const labels = {sent: "Ожидает ответа", accepted: "Принято", rejected: "Отказ"};
      const badge = document.getElementById("invite-status"); badge.textContent = labels[state]; badge.className = "tag " + ({sent: "tag-purple", accepted: "tag-success", rejected: "tag-red"}[state]);
      inviteActions.querySelectorAll("[data-invite-answer]").forEach(button => button.disabled = state !== "sent");
      document.getElementById("invite-contact").hidden = !(state === "accepted" && privacy().contacts);
      document.getElementById("invite-decision").textContent = state === "sent" ? "Решение ещё не принято." : state === "accepted" ? (privacy().contacts ? "Демо-приглашение принято. Синтетический контакт открыт компании." : "Демо-приглашение принято. Передача контакта отключена в демо-настройках.") : "Демо-приглашение отклонено. Контакт остаётся скрытым.";
    };
    inviteActions.querySelectorAll("[data-invite-answer]").forEach(button => button.addEventListener("click", () => { if (read("invitation:" + id, "sent") !== "sent") return; write("invitation:" + id, button.dataset.inviteAnswer); update(); notify("Решение показано только в демонстрации."); }));
    inviteActions.querySelector("[data-invite-reset]").addEventListener("click", () => { write("invitation:" + id, "sent"); update(); }); update();
  }
  document.querySelectorAll("[data-demo-form]").forEach(form => {
    if (form.dataset.demoForm === "privacy") {
      const saved = privacy(); form.querySelectorAll("input[type=checkbox]").forEach(input => input.checked = saved[input.name] ?? true);
    }
    form.addEventListener("submit", event => {
      event.preventDefault(); const type = form.dataset.demoForm;
      if (type === "invitation") {
        const low = Number(form.elements.salary_from.value), high = Number(form.elements.salary_to.value);
        const error = form.querySelector("[data-demo-error]"); error.hidden = low <= high;
        if (low > high) { form.elements.salary_from.focus(); return; }
        notify("Демо-отправка показана. Настоящее приглашение не отправлено.");
      } else if (type === "privacy") {
        const value = {}; form.querySelectorAll("input[type=checkbox]").forEach(input => value[input.name] = input.checked); write("privacy", value);
        document.getElementById("privacy-status").textContent = "Демо-настройки сохранены в текущей вкладке. Настоящий профиль не изменён."; notify("Сохранено только в демонстрации.");
      } else { write("need", Array.from(form.querySelectorAll("input,textarea,select")).map(input => input.value)); notify("Демо-потребность сохранена только в этой вкладке."); }
    });
    if (form.dataset.demoForm === "need") { const saved = read("need"); if (saved) form.querySelectorAll("input,textarea,select").forEach((input,index) => { if (saved[index] !== undefined) input.value = saved[index]; }); }
  });
  const link = document.querySelector("[data-fsp-link]");
  if (link) {
    link.addEventListener("click", () => { link.disabled = true; document.querySelector("[data-fsp-import]").disabled = false; document.getElementById("fsp-state").textContent = "Демо-участник demo-1 выбран. Личность не подтверждена."; });
    document.querySelector("[data-fsp-import]").addEventListener("click", () => { document.getElementById("fsp-achievements").hidden = false; document.getElementById("fsp-state").textContent = "Показано одно синтетическое достижение. Повторное действие не добавляет дубли."; notify("Демо-импорт. Запрос к реестру не выполнялся."); });
  }
  document.querySelector("[data-print-resume]")?.addEventListener("click", () => window.print());
});

// Live communication remains on the existing authenticated HTTP stack.
document.addEventListener('DOMContentLoaded', () => {
  const poll = (task, interval) => {
    const tick = async () => {
      if (!document.hidden) await task();
      window.setTimeout(tick, interval);
    };
    window.setTimeout(tick, interval);
  };
  const history=document.querySelector('[data-chat-feed]');
  if(history){
    const status=document.querySelector('[data-chat-status]');
    let denied=false;
    history.scrollTop=history.scrollHeight;
    poll(async()=>{
      if(denied) return;
      try{
        const response=await fetch(history.dataset.chatFeed+'?after='+history.dataset.lastMessage,{cache:'no-store'});
        if([401,403,404].includes(response.status)){denied=true;status.textContent='Доступ к переписке закрыт. Обновите состояние входа или согласия.';return;}
        if(!response.ok) throw new Error('feed');
        const data=await response.json();
        const compose=document.querySelector('[data-chat-compose]');
        if(compose){
          compose.hidden=!data.can_send;
          if(!data.can_send) compose.querySelectorAll('textarea,button').forEach(field=>{field.disabled=true;field.dataset.revokedDisabled='';});
          else compose.querySelectorAll('[data-revoked-disabled]').forEach(field=>{field.disabled=false;delete field.dataset.revokedDisabled;});
        }
        const closed=document.querySelector('[data-chat-closed]');if(closed) closed.hidden=Boolean(data.can_send);
        const meeting=document.querySelector('[data-chat-meeting]');if(meeting) meeting.hidden=!data.can_send;
        if(!data.can_view) document.querySelector('[data-chat-context]')?.remove();
        const atBottom=history.scrollHeight-history.scrollTop-history.clientHeight<60;
        for(const message of data.messages){
          history.querySelector('[data-chat-empty]')?.remove();
          const article=document.createElement('article');article.className='message-bubble'+(message.own?' message-own':'');
          const label=document.createElement('p');label.className='small muted';label.textContent=(message.own?'вы':history.dataset.peer)+' · '+new Date(message.created_at).toLocaleString('ru-RU');
          const body=document.createElement('p');body.className='matching-text';body.textContent=message.body;
          article.append(label);if(message.technical){const mark=document.createElement('p');mark.className='muted small';mark.dataset.technicalMessage='';mark.textContent='Автоматическое сообщение';article.append(mark);}article.append(body);history.append(article);history.dataset.lastMessage=String(message.id);
        }
        if(atBottom) history.scrollTop=history.scrollHeight;
        status.textContent='Сообщения обновляются автоматически.';
      }catch{status.textContent='Не удалось обновить сообщения. Повторное подключение выполняется автоматически.';}
    },2000);
  }
  const inbox=document.querySelector('[data-inbox-feed]');
  if(inbox){
    const status=document.querySelector('[data-inbox-status]');
    let denied=false;
    poll(async()=>{
      if(denied) return;
      try{
        const response=await fetch(inbox.dataset.inboxFeed,{cache:'no-store'});
        if([401,403,404].includes(response.status)){denied=true;status.textContent='Доступ закрыт. Проверьте состояние входа.';return;}
        if(!response.ok) throw new Error('inbox');
        const doc=new DOMParser().parseFromString(await response.text(),'text/html');
        const incoming=doc.querySelector('[data-inbox-feed]');
        if(!incoming) throw new Error('inbox');
        if(incoming.innerHTML!==inbox.innerHTML && !inbox.contains(document.activeElement)) inbox.replaceChildren(...incoming.childNodes);
        status.textContent='Диалоги обновляются автоматически.';
      }catch{status.textContent='Не удалось обновить диалоги. Подключение повторится автоматически.';}
    },5000);
  }
  const form=document.querySelector('[data-calendar-form]');
  if(form){
    document.querySelectorAll('[data-meeting-date]').forEach(button=>button.addEventListener('click',()=>{
      document.querySelectorAll('[data-meeting-date]').forEach(day=>day.setAttribute('aria-pressed',String(day===button)));
      const input=form.elements.scheduled_at;
      const time=input.value.split('T')[1]||'09:00';
      input.value=button.dataset.meetingDate+'T'+time;
      document.querySelector('[data-calendar-selection]').textContent='Выбрана дата '+button.dataset.meetingDate+'. Укажите время в часовом поясе встречи.';
      form.scrollIntoView({block:'nearest'});input.focus({preventScroll:true});
    }));
  }
});
