export function initCapacity() {
  const form = document.querySelector('form[data-capacity-url]');
  if (!form) return;
  const priority = form.querySelector('#id_priority');
  const program = form.querySelector('#id_program');
  const project = form.querySelector('#id_project_entity');
  const role = form.querySelector('#id_requester_role_context');
  const message = form.querySelector('[data-capacity-message]');
  const confirm = form.querySelector('[data-last-credit]');
  const submit = form.querySelector('button[name="action"][value="submit"]');
  const creditCodes = new Set(JSON.parse(form.dataset.creditPriorities || '[]'));
  let sequence = 0;
  async function refresh() {
    const current = ++sequence;
    confirm.hidden = true;
    confirm.querySelector('input').checked = false;
    submit.disabled = false;
    message.textContent = '';
    if (!creditCodes.has(priority.value)) return;
    const selectedRole = role?.value || role?.querySelector('option')?.value || '';
    const programId = program?.value || '';
    const projectId = project?.value || '';
    if ((selectedRole === 'PROGRAM_MANAGER' && !programId) || (selectedRole === 'PROJECT_MANAGER' && !projectId) || !selectedRole) {
      submit.disabled = true;
      message.textContent = 'برای اولویت اعتباری، طرح یا پروژهٔ مجاز را انتخاب کنید.';
      return;
    }
    submit.disabled = true;
    message.textContent = 'در حال بررسی اعتبار…';
    try {
      const url = new URL(form.dataset.capacityUrl, window.location.href);
      for (const [key, value] of Object.entries({ priority: priority.value, service: form.dataset.serviceId,
        role: selectedRole, program: programId, project: projectId })) url.searchParams.set(key, value);
      const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (current !== sequence) return;
      if (!data.available) {
        message.textContent = data.remaining === 0 ? 'اعتبار این طرح و اداره تمام شده است.' : 'تخصیص فعال برای این اولویت وجود ندارد.';
        return;
      }
      submit.disabled = false;
      message.textContent = `${data.remaining} اعتبار برای این طرح و اداره باقی مانده است.`;
      if (data.last_credit) {
        confirm.hidden = false;
        message.textContent += ' این آخرین اعتبار است؛ برای ثبت نهایی تأیید کنید.';
      }
    } catch {
      if (current === sequence) message.textContent = 'اعتبار قابل بررسی نیست. دوباره تلاش کنید.';
    }
  }
  for (const field of [priority, program, project, role]) field?.addEventListener('change', refresh);
  form.addEventListener('submit', event => {
    if (event.submitter?.value !== 'submit') return;
    if (submit.disabled || (!confirm.hidden && !confirm.querySelector('input').checked)) {
      event.preventDefault();
      if (!confirm.hidden) message.textContent = 'برای استفاده از آخرین اعتبار، گزینهٔ تأیید را انتخاب کنید.';
      message.focus();
    }
  });
  refresh();
}
