export function initJalaliAccessibility() {
  const digits = (value) => String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[digit]);
  document.querySelectorAll('.date-trigger').forEach((trigger) => {
    trigger.setAttribute('aria-haspopup', 'true');
    trigger.addEventListener('click', () => {
      requestAnimationFrame(() => {
        const popup = document.querySelector('.calendar-pop');
        if (!popup) return;
        popup.setAttribute('role', 'group');
        popup.setAttribute('aria-label', 'انتخاب تاریخ شمسی');
        trigger.setAttribute('aria-expanded', 'true');
        const decorate = () => {
          popup.querySelector('[data-next="1"]')?.setAttribute('aria-label', 'ماه بعد');
          popup.querySelector('[data-next="-1"]')?.setAttribute('aria-label', 'ماه قبل');
          popup.querySelectorAll('button.blank').forEach((button) => { button.disabled = true; button.setAttribute('aria-hidden', 'true'); });
          popup.querySelectorAll('button[data-day]').forEach((button) => {
            button.setAttribute('aria-label', `روز ${digits(button.dataset.day)}`);
            if (button.classList.contains('selected')) button.setAttribute('aria-pressed', 'true');
          });
        };
        decorate();
        const observer = new MutationObserver(decorate);
        observer.observe(popup, { childList: true });
        (popup.querySelector('button.selected') || popup.querySelector('button[data-day]:not(:disabled)'))?.focus();
        popup.addEventListener('keydown', (event) => {
          const days = [...popup.querySelectorAll('button[data-day]:not(:disabled)')];
          const index = days.indexOf(document.activeElement);
          const offsets = { ArrowRight: -1, ArrowLeft: 1, ArrowUp: -7, ArrowDown: 7 };
          if (event.key in offsets && index >= 0) {
            event.preventDefault(); days[Math.max(0, Math.min(days.length - 1, index + offsets[event.key]))]?.focus();
          } else if (event.key === 'Home' || event.key === 'End') {
            event.preventDefault(); days[event.key === 'Home' ? 0 : days.length - 1]?.focus();
          } else if (event.key === 'PageUp' || event.key === 'PageDown') {
            event.preventDefault(); popup.querySelector(`[data-next="${event.key === 'PageUp' ? '-1' : '1'}"]`)?.click();
            popup.querySelector('button[data-day]:not(:disabled)')?.focus();
          }
        });
        popup.addEventListener('click', (event) => { if (event.target.closest('[data-day]')) requestAnimationFrame(() => trigger.focus()); });
        const close = (event) => {
          if (event.key === 'Escape') requestAnimationFrame(() => trigger.focus());
        };
        document.addEventListener('keydown', close);
        const removal = new MutationObserver(() => {
          if (!popup.isConnected) {
            trigger.setAttribute('aria-expanded', 'false');
            observer.disconnect(); removal.disconnect(); document.removeEventListener('keydown', close);
          }
        });
        removal.observe(document.body, { childList: true });
      });
    });
  });
}
