(() => {
  let current = null;
  const status = document.getElementById('status');
  const api = async (path, options) => {
    const response = await fetch('../../api/evidence-runs' + path, {credentials:'same-origin', ...options});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
    return data;
  };
  const history = () => {document.getElementById('review-history').textContent = (current.reviews || []).map(r => `${r.actor}: ${r.scope} ${r.unit_key || ''} ${r.standard_identifier} — ${r.decision}: ${r.reason}`).join('\n');};
  document.getElementById('report-file').addEventListener('change', () => {current = null; document.getElementById('review-panel').hidden = true;});
  document.getElementById('list-runs').addEventListener('click', async () => {
    try {const data = await api(''); const select = document.getElementById('saved-run'); select.replaceChildren(new Option('Choose a run', ''));
      for (const item of data.items) select.add(new Option(`${item.id}: ${item.course_name} (${item.mode})`, item.id));
      status.textContent = data.migration_required ? 'Apply the evidence workflow migration to enable saved runs.' : `${data.items.length} saved runs.`;
    } catch(e) {status.textContent = e.message;}
  });
  document.getElementById('saved-run').addEventListener('change', async e => {
    if (!e.target.value) return;
    try {current = await api('/' + e.target.value); window.renderEvidenceReport(current.payload); document.getElementById('review-panel').hidden = false; history(); status.textContent = 'Saved artifact loaded.';} catch(error) {status.textContent = error.message;}
  });
  document.getElementById('review-form').addEventListener('submit', async e => {
    e.preventDefault(); if (!current) return;
    const scope = document.getElementById('review-scope').value;
    const body = {source_fingerprint:current.payload.manifest.input_sha256, scope,
      unit_key:scope === 'unit' ? document.getElementById('review-unit').value : null,
      standard_id:document.getElementById('review-standard').value, decision:document.getElementById('review-decision').value,
      actor:document.getElementById('review-actor').value, reason:document.getElementById('review-reason').value};
    try {await api('/' + current.id + '/reviews', {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      current = await api('/' + current.id); history(); status.textContent = 'Decision recorded. Nothing published.';
    } catch(error) {status.textContent = error.message;}
  });
})();
