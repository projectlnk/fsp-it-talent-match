document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-need-select]').forEach(select => {
    select.addEventListener('change', () => select.form.requestSubmit());
  });
  const form = document.querySelector('[data-team-need-form]');
  if (!form) return;
  const list = form.querySelector('[data-need-positions]');
  const add = form.querySelector('[data-add-position]');
  let nextIndex = list.children.length;
  const update = () => {
    const positions = list.querySelectorAll('[data-need-position]');
    positions.forEach((position, index) => {
      position.querySelector('[data-position-number]').textContent = index + 1;
      position.querySelector('[data-remove-position]').disabled = positions.length === 1;
    });
    add.disabled = positions.length >= 10;
  };
  add.addEventListener('click', () => {
    if (list.children.length >= 10) return;
    const fragment = form.querySelector('[data-position-template]').content.cloneNode(true);
    fragment.querySelectorAll('[name]').forEach(input => { input.name = input.name.replace('__INDEX__', nextIndex); });
    fragment.querySelector('[name=position_index]').value = nextIndex++;
    const name = fragment.querySelector('input[name$="_name"]');
    list.append(fragment); update(); name.focus();
  });
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-remove-position]');
    if (!button || list.children.length <= 1) return;
    button.closest('[data-need-position]').remove(); update(); add.focus();
  });
  update();
});
