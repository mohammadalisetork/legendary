export function initDialogs() {
  const form = document.querySelector('form[data-confirm-archive]');
  const dialog = document.getElementById('archive-confirm');
  if (!form || !dialog || typeof dialog.showModal !== 'function') return;
  const trigger = form.querySelector('button[type="submit"], button:not([type])');
  form.addEventListener('submit', (event) => {
    if (form.elements.namedItem('status')?.value !== 'ARCHIVED' || form.dataset.confirmed === 'true') return;
    event.preventDefault();
    dialog.showModal();
    dialog.querySelector('[data-dialog-cancel]').focus();
  });
  dialog.querySelector('[data-dialog-cancel]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-dialog-confirm]').addEventListener('click', () => {
    dialog.close(); form.dataset.confirmed = 'true'; form.requestSubmit(trigger);
  });
  dialog.addEventListener('close', () => trigger?.focus());
}
