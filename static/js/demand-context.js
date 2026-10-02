export function initDemandContext() {
  const form = document.querySelector('form[data-demand-context]');
  const role = form?.querySelector('#id_requester_role_context');
  const program = form?.querySelector('#id_program');
  const project = form?.querySelector('#id_project_entity');
  const status = form?.querySelector('[data-demand-project-status]');
  if (!form || !project) return;
  let sequence = 0;
  const programField = program?.closest('.field');
  const roleValue = () => role?.value || role?.querySelector('option')?.value || 'PROJECT_MANAGER';
  const showRoleContext = () => {
    const isProgram = roleValue() === 'PROGRAM_MANAGER';
    if (programField) programField.hidden = !isProgram;
    project.required = !isProgram;
  };
  form.addEventListener('submit', (event) => {
    if (form.dataset.demandLoading === 'true') {
      event.preventDefault();
      status.textContent = 'پس از دریافت فهرست پروژه‌ها، درخواست را ارسال کنید.';
      program?.focus();
    }
  }, { capture: true });
  const load = async (keepValue = true) => {
    const requestNumber = ++sequence;
    const selected = keepValue ? project.value : '';
    const selectedRole = roleValue();
    if (selectedRole === 'PROGRAM_MANAGER' && !program?.value) {
      project.replaceChildren(new Option('ابتدا طرح را انتخاب کنید', ''));
      project.disabled = false;
      form.dataset.demandLoading = 'false';
      status.textContent = '';
      return;
    }
    form.dataset.demandLoading = 'true';
    project.disabled = true;
    status.textContent = 'در حال دریافت پروژه‌های مجاز…';
    try {
      const url = new URL(form.dataset.projectOptionsUrl, window.location.href);
      url.searchParams.set('role', selectedRole);
      if (selectedRole === 'PROGRAM_MANAGER') url.searchParams.set('program', program.value);
      const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('درخواست فهرست پروژه‌ها ناموفق بود.');
      const data = await response.json();
      if (requestNumber !== sequence) return;
      project.replaceChildren(new Option(selectedRole === 'PROGRAM_MANAGER' ? 'بدون انتخاب پروژه' : 'پروژه را انتخاب کنید', ''));
      for (const item of data.projects) {
        const option = new Option(`${item.name} · ${item.code}`, item.id);
        project.add(option);
      }
      if (selected && [...project.options].some((item) => item.value === selected)) project.value = selected;
      project.dispatchEvent(new Event('change'));
      status.textContent = data.projects.length ? '' : 'برای این محدوده پروژهٔ فعالی وجود ندارد.';
    } catch {
      if (requestNumber === sequence) status.textContent = 'فهرست پروژه‌ها دریافت نشد؛ زمینه را دوباره انتخاب کنید.';
    } finally {
      if (requestNumber === sequence) { project.disabled = false; form.dataset.demandLoading = 'false'; }
    }
  };
  showRoleContext();
  role?.addEventListener('change', () => { showRoleContext(); load(false); });
  program?.addEventListener('change', () => load(false));
  if (program?.value && roleValue() === 'PROGRAM_MANAGER') load(true);
  else if (!program && roleValue() === 'PROJECT_MANAGER') load(true);
}
