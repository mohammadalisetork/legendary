export function initForms() {
  const firstError = document.querySelector('form .field.has-error input:not([type="hidden"]), form .field.has-error select, form .field.has-error textarea, form .field.has-error .date-trigger');
  firstError?.focus({ preventScroll: false });
  for (const form of document.querySelectorAll('form[data-submit-guard]')) {
    form.addEventListener('submit', (event) => {
      if (event.defaultPrevented) return;
      if (form.dataset.submitting === 'true') { event.preventDefault(); return; }
      form.dataset.submitting = 'true';
      const submitter = event.submitter;
      if (submitter?.name) {
        const field = document.createElement('input');
        field.type = 'hidden'; field.name = submitter.name; field.value = submitter.value;
        form.append(field);
      }
      form.querySelectorAll('button[type="submit"], button:not([type])').forEach((button) => {
        if (!button.disabled) { button.disabled = true; button.dataset.guardDisabled = 'true'; }
        if (button === submitter) button.setAttribute('aria-busy', 'true');
      });
    });
    window.addEventListener('pageshow', () => {
      form.dataset.submitting = 'false';
      form.querySelectorAll('button[data-guard-disabled]').forEach((button) => { button.disabled = false; button.removeAttribute('data-guard-disabled'); button.removeAttribute('aria-busy'); });
    });
  }
  for (const input of document.querySelectorAll('input[type="file"][data-file-preview]')) {
    const zone = input.closest('.upload-zone');
    const preview = zone?.querySelector('.file-preview');
    if (!zone || !preview) continue;
    const update = () => {
      const file = input.files?.[0];
      const limit = Number(input.dataset.maxSize || '0');
      if (!file) { preview.textContent = 'فایلی انتخاب نشده است.'; return; }
      if (limit && file.size > limit) {
        preview.textContent = 'حجم فایل بیشتر از حد مجاز است.';
        input.value = ''; return;
      }
      const extensions = input.accept.split(',').map((entry) => entry.trim().toLowerCase()).filter(Boolean);
      if (extensions.length && !extensions.some((extension) => file.name.toLowerCase().endsWith(extension))) {
        preview.textContent = 'نوع فایل مجاز نیست.';
        input.value = ''; return;
      }
      preview.textContent = `${file.name} · ${Math.ceil(file.size / 1024)} کیلوبایت`;
    };
    input.addEventListener('change', update);
    zone.addEventListener('dragover', (event) => { event.preventDefault(); zone.classList.add('is-dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('is-dragover'));
    zone.addEventListener('drop', (event) => {
      event.preventDefault(); zone.classList.remove('is-dragover');
      if (event.dataTransfer?.files.length && window.DataTransfer) {
        const transfer = new DataTransfer(); transfer.items.add(event.dataTransfer.files[0]);
        input.files = transfer.files; update();
      }
    });
    zone.querySelector('[data-clear-file]')?.addEventListener('click', () => { input.value = ''; update(); input.focus(); });
    update();
  }
  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;
      const visible = input.type === 'password';
      input.type = visible ? 'text' : 'password';
      button.value = visible ? 'پنهان‌کردن' : 'نمایش';
      button.setAttribute('aria-pressed', String(visible));
      input.focus();
    });
  });
}
