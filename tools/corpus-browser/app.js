/* Corpus Browser.
 *
 * Reads the store's own API. It computes nothing and writes nothing: every
 * number on the page came out of the corpus, so what you see here is what an
 * alignment run would see.
 *
 * The service address is a field rather than a constant, because this page is
 * opened straight from a file path and the service moves between machines.
 * It is remembered in localStorage, which is a per-browser convenience and
 * nothing more.
 */
'use strict';

const el = (id) => document.getElementById(id);
const statusBar = el('status');

const state = { lessons: [], currentId: null };

function api() {
  return el('api').value.replace(/\/+$/, '');
}

function say(message, isError) {
  statusBar.textContent = message || '';
  statusBar.classList.toggle('error', Boolean(isError));
}

async function get(path) {
  const response = await fetch(api() + path);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} on ${path}`);
  }
  return response.json();
}

function text(node, value) {
  node.textContent = value == null ? '' : String(value);
  return node;
}

function make(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content != null) node.textContent = content;
  return node;
}

/* ------------------------------------------------------------- loading */

async function loadSnapshots() {
  const data = await get('/snapshots');
  const select = el('snapshot');
  select.textContent = '';
  if (!data.items.length) {
    select.append(new Option('no corpus loaded', ''));
    return;
  }
  for (const s of data.items) {
    const when = (s.extracted_at || '').slice(0, 10);
    const label = `${s.source_commit.slice(0, 8)} · ${s.lesson_count} lessons` +
      (s.is_current ? ' · current' : '') + (when ? ` · ${when}` : '');
    const option = new Option(label, s.id);
    if (s.is_current) option.selected = true;
    select.append(option);
  }
}

async function loadCourses() {
  const snapshotId = el('snapshot').value;
  const select = el('course');
  select.textContent = '';
  if (!snapshotId) return;

  const data = await get('/courses?snapshot_id=' + encodeURIComponent(snapshotId));
  if (!data.items.length) {
    select.append(new Option('no curricula in this corpus', ''));
    return;
  }
  for (const c of data.items) {
    select.append(new Option(`${c.course_name} (${c.units.length} units)`, c.id));
  }
}

async function loadLessons() {
  const courseId = el('course').value;
  const list = el('unit-list');
  list.textContent = '';
  el('units-summary').textContent = '';
  if (!courseId) return;

  const data = await get('/lessons?course_id=' + encodeURIComponent(courseId));
  state.lessons = data.items;

  // Group by unit, keeping the order the API returned. That order is the
  // teaching order: unit position first, then the lesson's own position.
  const units = [];
  const byScript = new Map();
  for (const lesson of data.items) {
    if (!byScript.has(lesson.script_name)) {
      const unit = {
        script_name: lesson.script_name,
        unit_name: lesson.unit_name,
        displayed_number: lesson.displayed_number,
        lessons: []
      };
      byScript.set(lesson.script_name, unit);
      units.push(unit);
    }
    byScript.get(lesson.script_name).lessons.push(lesson);
  }

  el('units-summary').textContent =
    `${units.length} units · ${data.items.length} lessons`;

  units.forEach((unit, index) => {
    const details = make('details', 'unit');
    if (index === 0) details.open = true;

    const summary = document.createElement('summary');

    // A blank displayed number is a real value, not a missing one, and it is
    // shown as such. Position and displayed number disagree in real courses,
    // so the badge never falls back to the position.
    const badge = make('span', 'unit-num');
    if (unit.displayed_number) {
      badge.textContent = unit.displayed_number;
    } else {
      badge.textContent = 'no number';
      badge.classList.add('blank');
    }

    summary.append(
      badge,
      make('span', 'unit-name', unit.unit_name),
      make('span', 'unit-count', String(unit.lessons.length))
    );
    details.append(summary);

    for (const lesson of unit.lessons) {
      const button = make('button', 'lesson-btn');
      button.type = 'button';
      button.dataset.id = lesson.id;
      button.append(make('span', 'tok', lesson.lesson_token));
      button.append(document.createTextNode(lesson.lesson_name));
      if (!lesson.has_lesson_plan) {
        button.append(make('span', 'no-plan', ' · no plan'));
      }
      button.addEventListener('click', () => showLesson(lesson.id));
      details.append(button);
    }
    list.append(details);
  });
}

/* -------------------------------------------------------------- lesson */

function chip(label, kind) {
  return make('span', 'chip' + (kind ? ' ' + kind : ''), label);
}

function block(title) {
  const section = make('section', 'block');
  section.append(make('h3', null, title));
  return section;
}

function prose(markdown) {
  // The corpus stores authored markdown. This is a viewer, not a renderer:
  // the text is shown as written, so nothing can be silently reworded by a
  // half-finished markdown parser.
  return make('div', 'prose', markdown);
}

async function showLesson(id) {
  state.currentId = id;
  for (const button of document.querySelectorAll('.lesson-btn')) {
    button.setAttribute('aria-current',
      String(Number(button.dataset.id) === Number(id)));
  }

  const view = el('lesson');
  view.textContent = '';
  view.append(make('p', 'empty', 'Loading…'));

  let lesson;
  try {
    lesson = await get('/lessons/' + encodeURIComponent(id));
  } catch (err) {
    view.textContent = '';
    view.append(make('p', 'empty', 'Could not load that lesson. ' + err.message));
    return;
  }

  const plan = lesson.plan || {};
  const levels = lesson.levels || [];
  view.textContent = '';

  view.append(make('h2', 'lesson-title', lesson.lesson_name));
  view.append(make('p', 'crumb',
    `${lesson.unit_name} · ${lesson.script_name} · lesson ` +
    `${lesson.relative_position} of the unit, ${lesson.absolute_position} overall`));

  const chips = make('div', 'chips');
  chips.append(chip(lesson.stable_id, 'id'));
  chips.append(chip('hash ' + String(lesson.content_hash).slice(0, 10), 'id'));
  if (plan.duration_minutes) chips.append(chip(plan.duration_minutes + ' min', 'info'));
  chips.append(chip(levels.length + ' levels', 'info'));

  const words = levels.reduce((sum, lv) => sum + (lv.word_count || 0), 0);
  chips.append(chip(words.toLocaleString() + ' student words', 'info'));

  const choices = levels.filter((lv) => lv.context && lv.context.is_choice_option);
  if (choices.length) {
    chips.append(chip(choices.length + ' in a choice branch', 'warn'));
  }
  if (!lesson.has_lesson_plan) chips.append(chip('no lesson plan', 'warn'));
  if (!lesson.has_objectives) chips.append(chip('no authored objective', 'warn'));
  if (lesson.has_objectives) chips.append(chip('has objectives', 'good'));
  view.append(chips);

  if (!lesson.has_lesson_plan) {
    const note = block('Why this lesson has no plan');
    note.append(prose(
      'This is an assessment shell, a pre-assessment, or an end-of-unit ' +
      'survey. It still holds a position in the sequence, which is why the ' +
      'lesson numbers around it skip. Nothing here should be given an ' +
      'inferred objective.'));
    view.append(note);
  }

  if ((plan.objectives || []).length) {
    const section = block('Objectives');
    const list = make('ul', 'plain');
    for (const objective of plan.objectives) list.append(make('li', null, objective));
    section.append(list);
    view.append(section);
  }

  if ((plan.standards || []).length) {
    const section = block('Standards the authors cite');
    section.append(prose(
      'Their claims, not evidence. A strong prior and a useful cross-check, ' +
      'and wrong in both directions often enough to be checked.'));
    for (const s of plan.standards) {
      const item = make('div', 'std');
      item.append(make('code', null, s.shortcode));
      item.append(make('span', 'fw', s.framework));
      item.append(make('p', null, s.statement || '(not resolved to statement text)'));
      section.append(item);
    }
    view.append(section);
  }

  for (const [label, key] of [
    ['Overview', 'overview_md'],
    ['Student overview', 'student_overview_md'],
    ['Purpose', 'purpose_md'],
    ['Preparation', 'preparation_md'],
    ['Assessment opportunities', 'assessment_opportunities_md']
  ]) {
    if (plan[key]) {
      const section = block(label);
      section.append(prose(plan[key]));
      view.append(section);
    }
  }

  if ((plan.activities || []).length) {
    const section = block('Teaching guide');
    for (const activity of plan.activities) {
      for (const sec of activity.sections || []) {
        const card = make('div', 'section-card');
        const heading = make('h4', null,
          sec.name || sec.progression_name || 'Section');
        if (sec.duration_minutes) {
          heading.append(make('span', 'mins', '  ' + sec.duration_minutes + ' min'));
        }
        card.append(heading);
        if (sec.description_md) card.append(prose(sec.description_md));
        for (const tip of sec.tips || []) {
          if (!tip || !tip.markdown) continue;
          const note = make('div', 'tip');
          note.append(make('b', null, (tip.type || 'tip') + ': '));
          note.append(document.createTextNode(tip.markdown));
          card.append(note);
        }
        if (sec.remarks_md) {
          const note = make('div', 'tip');
          note.append(make('b', null, 'remarks: '));
          note.append(document.createTextNode(sec.remarks_md));
          card.append(note);
        }
        section.append(card);
      }
    }
    view.append(section);
  }

  if (levels.length) {
    const section = block('Student instructions, in the order a student meets them');
    levels.forEach((lv, index) => {
      const details = make('details', 'level');
      const summary = document.createElement('summary');
      summary.append(make('span', 'level-n', String(index + 1)));
      summary.append(make('span', 'level-name',
        lv.title || lv.level_name));

      const context = lv.context || {};
      const marks = [lv.level_type, (lv.word_count || 0) + ' words'];
      if (context.is_choice_option) marks.push('one option of a choice');
      if (context.is_assessment) marks.push('assessment');
      if (context.is_bonus) marks.push('bonus');
      if (lv.has_starter_code) marks.push('starter code');
      if (lv.has_validation) marks.push('validated');
      summary.append(make('span', 'level-meta', marks.join(' · ')));
      details.append(summary);

      const body = make('div', 'level-body');
      body.append(make('p', 'level-id', lv.level_name));

      if (context.is_choice_option) {
        const warn = make('div', 'tip');
        warn.append(make('b', null, 'Choice branch: '));
        warn.append(document.createTextNode(
          'only some students do this, so a claim resting on it is met by a ' +
          'fraction of the class. Parent: ' + (context.choice_parent || '—')));
        body.append(warn);
      }

      if (lv.student_text) {
        body.append(prose(lv.student_text));
      } else {
        body.append(prose(
          'No student text. For a code template or an interactive level this ' +
          'is correct — the activity is the interface, not words.'));
      }

      if ((lv.answer_options || []).length) {
        const options = make('ul', 'opts');
        for (const option of lv.answer_options) {
          const item = make('li', option.correct ? 'right' : null,
            option.text + (option.correct ? '  ✓' : ''));
          options.append(item);
        }
        body.append(options);
      }
      details.append(body);
      section.append(details);
    });
    view.append(section);
  }

  if ((plan.resources || []).length) {
    const section = block('Resources');
    for (const r of plan.resources) {
      const item = make('div', 'res');
      const link = document.createElement('a');
      link.href = r.url || '#';
      link.textContent = r.name || r.url;
      link.rel = 'noopener noreferrer';
      link.target = '_blank';
      item.append(link);
      if (r.is_answer_key) {
        item.append(document.createTextNode(' '));
        item.append(chip('answer key — restricted', 'warn'));
      }
      section.append(item);
    }
    view.append(section);
  }

  const raw = block('The record itself');
  const details = make('details');
  details.append(make('summary', null, 'Show the JSON this page was built from'));
  const pre = make('pre', 'raw', JSON.stringify(lesson, null, 2));
  details.append(pre);
  raw.append(details);
  view.append(raw);

  view.scrollTop = 0;
}

/* --------------------------------------------------------------- wiring */

async function refreshAll() {
  try {
    say('Loading…');
    await loadSnapshots();
    await loadCourses();
    await loadLessons();
    say(`Reading ${api()}`);
  } catch (err) {
    say(`Could not reach the service at ${api()} — ${err.message}. ` +
        'Is it running? docker compose -f service/docker-compose.yml up', true);
  }
}

el('pickers').addEventListener('submit', (event) => {
  event.preventDefault();
  try {
    localStorage.setItem('corpus-browser-api', api());
  } catch (ignored) { /* private windows and blocked storage are fine */ }
  refreshAll();
});

el('snapshot').addEventListener('change', async () => {
  try {
    await loadCourses();
    await loadLessons();
  } catch (err) { say(err.message, true); }
});

el('course').addEventListener('change', async () => {
  try {
    await loadLessons();
  } catch (err) { say(err.message, true); }
});

try {
  const saved = localStorage.getItem('corpus-browser-api');
  if (saved) el('api').value = saved;
} catch (ignored) { /* see above */ }

refreshAll();
