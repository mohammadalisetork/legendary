export function initOnboardingTour() {
  const dialog = document.querySelector('[data-onboarding-tour]');
  if (!dialog || typeof dialog.showModal !== 'function') return;

  const order = ['welcome', 'find-service', 'departments', 'recent-requests', 'workspace'];
  const steps = [];
  for (const target of [...document.querySelectorAll('[data-tour-step]')].sort((a, b) => order.indexOf(a.dataset.tourStep) - order.indexOf(b.dataset.tourStep))) {
    const key = target.dataset.tourStep;
    if (!steps.some((step) => step.key === key)) steps.push({
      key,
      target,
      title: target.dataset.tourTitle || 'آشنایی با سامانه',
      description: target.dataset.tourDescription || '',
    });
  }
  if (!steps.length) return;

  const count = dialog.querySelector('[data-tour-count]');
  const title = dialog.querySelector('[data-tour-title-text]');
  const description = dialog.querySelector('[data-tour-description-text]');
  const previous = dialog.querySelector('[data-tour-previous]');
  const next = dialog.querySelector('[data-tour-next]');
  const skip = dialog.querySelector('[data-tour-skip]');
  const csrf = dialog.querySelector('[name=csrfmiddlewaretoken]')?.value;
  let index = 0;
  let saving = false;

  const render = () => {
    steps.forEach(({ target }, stepIndex) => target.classList.toggle('is-tour-target', stepIndex === index));
    const current = steps[index];
    count.textContent = `گام ${index + 1} از ${steps.length}`;
    title.textContent = current.title;
    description.textContent = current.description;
    previous.hidden = index === 0;
    next.textContent = index === steps.length - 1 ? 'پایان' : 'بعدی';
    current.target.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    (index === 0 ? next : previous).focus();
  };

  const finish = async (action) => {
    if (saving) return;
    saving = true;
    skip.disabled = true;
    next.disabled = true;
    previous.disabled = true;
    try {
      const body = new URLSearchParams({ action, manual: dialog.dataset.manual, csrfmiddlewaretoken: csrf || '' });
      const response = await fetch(dialog.dataset.stateUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'X-CSRFToken': csrf || '' },
        body,
      });
      if (!response.ok) throw new Error('tour state request failed');
      steps.forEach(({ target }) => target.classList.remove('is-tour-target'));
      dialog.close();
    } catch {
      saving = false;
      skip.disabled = false;
      next.disabled = false;
      previous.disabled = false;
      description.textContent = 'ذخیره نشد. اتصال را بررسی کنید و دوباره تلاش کنید.';
      next.focus();
    }
  };

  previous.addEventListener('click', () => { if (index > 0) { index -= 1; render(); } });
  next.addEventListener('click', () => { if (index < steps.length - 1) { index += 1; render(); } else finish('finish'); });
  skip.addEventListener('click', () => finish('skip'));
  dialog.addEventListener('cancel', (event) => { event.preventDefault(); finish('skip'); });
  dialog.addEventListener('close', () => steps.forEach(({ target }) => target.classList.remove('is-tour-target')));
  dialog.showModal();
  render();
}
