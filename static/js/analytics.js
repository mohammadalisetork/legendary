const source = document.getElementById('report-chart-data');
if (source && window.Chart) {
  const data = JSON.parse(source.textContent);
  const ink = '#215681', accent = '#56a5ba', muted = '#8c9fb0';
  const get = key => data[key] || [];
  const simple = (key, horizontal = false) => ({
    type: 'bar',
    data: { labels: get(key).map(row => row.name), datasets: [{ label: 'تعداد', data: get(key).map(row => row.total), backgroundColor: ink, borderRadius: 3, maxBarThickness: 28 }] },
    options: { indexAxis: horizontal ? 'y' : 'x', onClick(event, elements) { const row = get(key)[elements[0]?.index]; if (row?.url) window.location.assign(row.url); },
      plugins: { legend: { display: false, rtl: true }, tooltip: { rtl: true, textDirection: 'rtl' } } },
  });
  const configs = {
    trend: { type: 'line', data: { labels: get('trend').map(row => row.date), datasets: [
      { label: 'درخواست جدید', data: get('trend').map(row => row.new), borderColor: ink, backgroundColor: ink, tension: .2 },
      { label: 'تکمیل در بازه', data: get('trend').map(row => row.completed), borderColor: accent, backgroundColor: accent, tension: .2 }] } },
    department: simple('department', true), status: simple('status'), sla: simple('sla'), service: simple('service', true),
    resolution: simple('resolution'), aging: simple('aging'), owner: simple('owner', true), flow: simple('flow'), priority: simple('priority'),
    matrix: { type: 'bar', data: { labels: get('matrix').map(row => `${row.program} · ${row.department}`), datasets: [{ label: 'تقاضا', data: get('matrix').map(row => row.total), backgroundColor: ink, maxBarThickness: 26 }] },
      options: { indexAxis: 'y', onClick(event, elements) { const row = get('matrix')[elements[0]?.index]; if (row?.url) window.location.assign(row.url); }, plugins: { legend: { display: false, rtl: true }, tooltip: { rtl: true, textDirection: 'rtl' } } } },
    credit: simple('credit', true),
  };
  document.querySelectorAll('[data-report-chart]').forEach(canvas => {
    const config = configs[canvas.dataset.reportChart]; if (!config) return;
    config.options = { responsive: true, maintainAspectRatio: false, locale: 'fa-IR', color: muted, animation: false,
      scales: { x: { ticks: { maxRotation: 0, autoSkip: true }, grid: { color: '#e5ebf0' } }, y: { ticks: { autoSkip: true }, grid: { color: '#e5ebf0' } } }, ...config.options };
    new Chart(canvas, config);
  });
}
const select = name => document.querySelector(`.report-filters select[name="${name}"]`);
const department = select('department'), program = select('program'), project = select('project'), family = select('family'), service = select('service');
function dependent(parent, child, attribute) {
  if (!parent || !child) return;
  const refresh = () => { for (const option of child.options) { if (!option.value) continue; option.hidden = Boolean(parent.value && option.dataset[attribute] !== parent.value); option.disabled = option.hidden; }
    if (child.selectedOptions[0]?.disabled) child.value = ''; };
  parent.addEventListener('change', refresh); refresh();
}
dependent(program, project, 'program'); dependent(department, family, 'department');
if (service) {
  const refresh = () => { for (const option of service.options) { if (!option.value) continue;
      option.hidden = Boolean((family?.value && option.dataset.family !== family.value) || (department?.value && option.dataset.department !== department.value)); option.disabled = option.hidden; }
    if (service.selectedOptions[0]?.disabled) service.value = ''; };
  family?.addEventListener('change', refresh); department?.addEventListener('change', refresh); refresh();
}
