/* Shared by the offline artifact and the internal workbench. Data is text only. */
(() => {
  const el = (tag, text, parent) => { const e = document.createElement(tag); if (text != null) e.textContent = String(text); if (parent) parent.append(e); return e; };
  const show = (data) => {
    const root = document.getElementById('report'); root.replaceChildren();
    const m = data.manifest, state = data.state, coverage = state.coverage;
    el('h2', m.course_name, root);
    el('p', `Mode: ${m.mode} · ${m.stage} · ${Object.keys(state.inventories).length}/${m.expected_lesson_count} lessons synthesized`, root);
    el('p', 'Proposed curriculum judgments. Exact quotations are checked, but semantic alignment still needs review. Curriculum coverage is not student mastery.', root).className = 'notice';
    el('p', `Scope: ${m.scope_note || m.scope_origin}`, root);
    const comparison = el('section', null, root); el('h2', 'Human and automated comparison', comparison);
    el('p', `Historical baseline: ${data.comparison.baseline_pairs} pairs. Human mapping: ${data.comparison.human_pairs}. Shared: ${data.comparison.baseline_human_overlap}.`, comparison);
    el('p', data.comparison.proposed_pairs == null ? 'New alignment has not run.' : `New contributions: ${data.comparison.proposed_pairs}. Shared with human mapping: ${data.comparison.proposed_human_overlap}.`, comparison);
    el('p', data.comparison.note, comparison).className = 'meta';
    for (const warning of m.pathway_warnings || []) el('p', warning, root).className = 'notice';
    const evidence = Object.fromEntries(data.sources.map(s => [s.stable_id, s]));
    const allItems = Object.fromEntries(Object.values(state.inventories).flatMap(inv => inv.items.map(i => [i.item_id, i])));
    const itemDetails = (item, parent) => {
      const detail = el('details', null, parent); el('summary', `${item.kind}: ${item.student_action}`, detail);
      el('p', `${item.lesson_id} · ${item.subject} · ${item.independence}`, detail);
      el('p', `Artifact: ${item.expected_artifact || 'not specified'}`, detail);
      el('p', Object.keys(item.conditions).length ? `Pathway: ${JSON.stringify(item.conditions)}` : 'Shared task', detail);
      for (const cite of item.citations) { el('code', cite.source_id, detail); el('blockquote', cite.quote, detail); }
    };
    const outcomes = (values, parent) => {
      const scroll = el('div', null, parent); scroll.className = 'scroll'; const table = el('table', null, scroll);
      el('caption', 'Performance coverage; exposure and supporting contributions remain visible', table);
      const tr = el('tr', null, el('thead', null, table));
      for (const h of ['Standard', 'Coverage', 'Assessment at expected demand', 'Evidence']) {const th = el('th', h, tr); th.scope = 'col';}
      const body = el('tbody', null, table);
      for (const [sid, outcome] of Object.entries(values)) {
        const row = el('tr', null, body); el('th', sid, row).scope = 'row';
        el('td', outcome.coverage, row); el('td', outcome.assessed_at_expected_demand ? 'Yes, proposed' : 'Not established', row);
        const cell = el('td', null, row); el('p', outcome.evidence_sufficiency, cell);
        const detail = el('details', null, cell); el('summary', 'Inspect requirements and source evidence', detail);
        for (const [rid, req] of Object.entries(outcome.requirements)) {
          const spec = (state.specs || []).find(s => s.standard_id === sid)?.requirements.find(r => r.requirement_id === rid);
          el('p', `${rid}: ${spec?.required_performance || spec?.quote || ''}`, detail);
          el('p', `Full across paths: ${req.full_on_all_paths}. Some performance across paths: ${req.performance_on_all_paths}.`, detail);
        }
        if (outcome.cross_pass_disagreements.length) el('p', `Review disagreement between passes: ${outcome.cross_pass_disagreements.join(', ')}`, detail).className = 'notice';
        for (const id of outcome.evidence_item_ids) if (allItems[id]) itemDetails(allItems[id], detail);
      }
    };
    const course = el('section', null, root); el('h2', 'Course coverage', course);
    if (coverage) outcomes(coverage.course, course); else el('p', 'Awaiting synthesized inventory and alignment. No new coverage conclusions.', course);
    const units = el('section', null, root); el('h2', 'Units and lesson evidence', units);
    const groups = {};
    for (const source of data.sources) (groups[source.unit_key] ||= []).push(source);
    for (const [key, lessons] of Object.entries(groups)) {
      const detail = el('details', null, units); el('summary', `${lessons[0].unit_name} · ${lessons.length} lessons`, detail);
      const summary = state.unit_summaries[key];
      if (summary) {el('p', summary.summary, detail); for (const step of summary.progression) {el('p', step.description, detail); for (const id of step.item_ids) if (allItems[id]) itemDetails(allItems[id], detail);}}
      else el('p', 'Unit synthesis has not run.', detail);
      if (coverage?.units[key]) outcomes(coverage.units[key].outcomes, detail);
      for (const lesson of lessons) {
        const ld = el('details', null, detail); el('summary', lesson.lesson_name, ld);
        const inv = state.inventories[lesson.stable_id];
        if (inv) for (const item of inv.items) itemDetails(item, ld);
        else el('p', `Inventory pending. ${lesson.sources.length} raw source passages retained.`, ld);
        for (const gap of lesson.gaps) el('p', `${gap.kind}: ${gap.name || ''}`, ld).className = 'meta';
      }
    }
    const failures = el('section', null, root); el('h2', 'Processing and provenance', failures);
    el('p', `Input: ${m.input_sha256}`, failures);
    el('pre', JSON.stringify({usage:m.usage, failures:state.failures}, null, 2), failures);
  };
  window.renderEvidenceReport = show;
  const embedded = document.getElementById('report-data');
  if (embedded) show(JSON.parse(embedded.textContent));
  const file = document.getElementById('report-file');
  file?.addEventListener('change', async () => {try {show(JSON.parse(await file.files[0].text()));} catch(e) {document.getElementById('status').textContent = e.message;}});
})();
