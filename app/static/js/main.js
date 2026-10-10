document.addEventListener("DOMContentLoaded", () => {
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
