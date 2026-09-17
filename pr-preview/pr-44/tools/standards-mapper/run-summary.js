/* run-summary.js — what this run is, and where it stands.
 *
 * The header, the four tiles and the publish banner. Reads the context
 * workbench.js builds; owns no fetching.
 *
 * The header names the work the way the person doing it would: the state's
 * framework, the grades it covers, the course it was run against. A run id is
 * not how anybody identifies their own work, so it appears once, quietly, at
 * the end of the line.
 *
 * There is no publish banner. It said in three lines what the status word in
 * the header line says in one, on every single run, forever. The rule it was
 * defending is still true and still enforced by the service - a run reaches a
 * district when a person approves it (contract/REVIEW-DESIGN.md) - it just
 * does not need a standing announcement on a screen whose whole job is the
 * reviewing that happens first.
 */

window.RunSummary = (function () {
  'use strict';

  var S = window.StandardsSource;
  var D = window.ReviewDecisions;

  var mount = document.getElementById('run-summary');
  var queueItems = [];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function showMessage(text) {
    mount.innerHTML = '';
    mount.appendChild(el('p', 'wb-note', text));
  }

  /* One tile. The number is what the eye lands on, so it is the larger of the
   * two and the label sits above it - a figure with its caption, not a
   * sentence to parse. */
  function tile(label, value, tone) {
    var wrap = el('div', 'wb-tile' + (tone ? ' wb-tile-' + tone : ''));
    wrap.appendChild(el('p', 'wb-tile-label', label));
    wrap.appendChild(el('p', 'wb-tile-value', String(value)));
    return wrap;
  }

  /* Standards still carrying something for a person to decide.
   *
   * This tile used to count records, and read 434 beside three tiles counting
   * standards. Two things were wrong with that. The number was inflated by a
   * join bug (fixed in the service: a record was emitted once per course
   * sharing its unit), and even correct it answered a different question from
   * its neighbours - "55 in scope, 41 matched, 434 to check, 14 not taught"
   * does not describe one set of things. All four count standards now. */
  function standardsPending() {
    return queueItems.filter(itemNeedsReview).length;
  }

  function itemNeedsReview(item) {
    return (item.records || []).some(function (record) {
      if (D.get(record.id)) { return false; }
      return record.review_status === 'proposed' || record.review_status === 'stale';
    });
  }

  /* The grades this run covers.
   *
   * Taken from the standards themselves, not from the set: a set's `scope` is
   * free text somebody may or may not have filled in - it is null on the
   * Oklahoma set - while grade_band is on every standard by the time one has
   * been ingested. The set's scope is the fallback, and saying nothing is
   * better than guessing. */
  /* [rank, value] for one band. Numeric bands sort by their first number;
   * anything lettered (K, PK) sorts ahead of all of them. */
  function gradeSortKey(band) {
    var first = String(band).split(/[^0-9A-Za-z]+/)[0];
    return /^\d+$/.test(first) ? [1, parseInt(first, 10)] : [0, first.toUpperCase()];
  }

  function gradeLabel(ctx) {
    var seen = {};
    (ctx.queue.items || []).forEach(function (item) {
      var band = item.standard && item.standard.grade_band;
      if (band) { seen[band] = true; }
    });

    /* Sorted by the grade they start at, not as strings. Alphabetically
     * "11-12" sorts before "9-10", which is how the header came to read
     * "Grades 11-12, 9-10". K and PK come before any number. */
    var bands = Object.keys(seen).sort(function (a, b) {
      var ka = gradeSortKey(a), kb = gradeSortKey(b);
      return (ka[0] - kb[0]) || (ka[1] < kb[1] ? -1 : ka[1] > kb[1] ? 1 : 0);
    });
    if (bands.length) {
      return 'Grades ' + bands.join(', ');
    }
    if (ctx.set && ctx.set.scope) {
      return ctx.set.scope;
    }
    return null;
  }

  /* "16 September 2026". Intl where it exists, the ISO date otherwise -
   * a date is worth showing even in a browser that will not format it. */
  function whenStarted(run) {
    if (!run.created_at) { return null; }
    try {
      return new Date(run.created_at).toLocaleDateString(undefined,
        { year: 'numeric', month: 'long', day: 'numeric' });
    } catch (error) {
      return String(run.created_at).slice(0, 10);
    }
  }

  function joinParts(parts) {
    return parts.filter(Boolean).join(' · ');
  }

  /* "AI Foundations: Exploring AI and CS, Semester 1". The column is null for
   * most courses, so the semester is appended only when there is one rather
   * than guessed at from the course name. */
  function courseLabel(ctx) {
    if (!ctx.course) { return null; }
    var name = ctx.course.course_name;
    var sem = ctx.course.semester;
    if (!sem) { return name; }
    return name + ', ' + (/^S\d$/.test(sem) ? 'Semester ' + sem.slice(1) : sem);
  }

  function heading(ctx) {
    var wrap = el('div', 'wb-run-head');

    var titleRow = el('div', 'wb-run-title-row');
    titleRow.appendChild(el('h3', 'wb-run-title',
      ctx.set ? ctx.set.title : 'Standards set ' + ctx.run.set_id));

    /* Which data this screen is reading. The old dashed "sample data" box
     * said this and only had one answer; now that the page reads a live
     * store it has two, and the honest thing is to name whichever it is. */
    titleRow.appendChild(el('span',
      'wb-pill ' + (S.mode === 'fixtures' ? 'wb-pill-warn' : 'wb-pill-concept'),
      S.mode === 'fixtures' ? 'Sample data' : 'Live service'));
    wrap.appendChild(titleRow);

    // State, grade, course. In that order, because that is how it is asked for.
    wrap.appendChild(el('p', 'wb-run-detail', joinParts([
      ctx.set ? ctx.set.framework : null,
      gradeLabel(ctx),
      courseLabel(ctx)
    ])));

    // The provenance line: which framework year, which course version, and
    // which of this pair's runs you are looking at.
    var position = ctx.position || { index: 1, total: 1 };
    wrap.appendChild(el('p', 'wb-run-detail', joinParts([
      ctx.set ? ctx.set.framework_year + ' framework' : null,
      'course version ' + ctx.run.snapshot_id,
      'by ' + ctx.run.grain,
      'run ' + position.index + ' of ' + position.total,
      S.runStatusWord(ctx.run),
      whenStarted(ctx.run) ? 'started ' + whenStarted(ctx.run) : null
    ])));

    return wrap;
  }

  function tiles(ctx) {
    var coverage = ctx.coverage;
    var wrap = el('div', 'wb-tiles');

    wrap.appendChild(tile('Standards in scope', coverage.in_scope.total));
    wrap.appendChild(tile('Matches found', coverage.in_scope.covered));
    wrap.appendChild(tile('Standards to check', standardsPending(), 'attention'));
    wrap.appendChild(tile('Not taught', coverage.buckets.not_addressed || 0));

    return wrap;
  }

  /* Two percentages are returned and both are true; they differ because scope
   * is a judgement. The contract is explicit that neither may be printed
   * without the scope note beside it, so the note is built into this function
   * rather than left for a caller to remember. */
  function percentages(ctx) {
    var coverage = ctx.coverage;
    var wrap = el('div', 'wb-percents');

    /* Two percentages exist because scope is a judgement and they usually
     * differ. When nothing is out of scope they are the same number, and
     * printing it twice in one sentence reads like a mistake rather than
     * like rigour. Say it once, and say why it is only once. */
    var scoped = coverage.in_scope;
    var whole = coverage.whole_framework;
    var same = scoped.percent === whole.percent && scoped.total === whole.total;

    wrap.appendChild(el('p', 'wb-percent-line', same
      ? scoped.percent + '% of the framework is covered (' + scoped.covered +
        ' of ' + scoped.total + '). Nothing is out of scope in this run, so ' +
        'the in-scope and whole-framework figures are the same number.'
      : scoped.percent + '% of the standards in scope are covered (' +
        scoped.covered + ' of ' + scoped.total + '). Across the whole ' +
        'framework it is ' + whole.percent + '% (' + whole.covered + ' of ' +
        whole.total + ').'));

    wrap.appendChild(el('p', 'wb-scope-note', 'Scope: ' + coverage.scope_note));

    if (coverage.covered_with_caveat) {
      wrap.appendChild(el('p', 'wb-caveat-note',
        coverage.covered_with_caveat + ' of those are covered only in part. ' +
        'Decide which number you quote before a state asks.'));
    }

    if (coverage.umbrella_excluded) {
      wrap.appendChild(el('p', 'wb-caveat-note',
        coverage.umbrella_excluded + ' heading row' +
        (coverage.umbrella_excluded === 1 ? ' is' : 's are') +
        ' left out of these totals. Counting them would count their children twice.'));
    }

    return wrap;
  }

  /* The buckets have to sum to the candidate set. When they do not, a standard
   * has no outcome row and every total on this screen is short by at least
   * one. Say so loudly and name the two numbers: a total you cannot justify is
   * worse than no total. */
  function countCheckWarning(ctx) {
    var check = ctx.coverage.count_check;
    if (!check || check.ok) {
      return null;
    }

    var warning = el('div', 'wb-banner wb-banner-problem');
    warning.setAttribute('role', 'alert');
    warning.appendChild(el('p', 'wb-banner-title', 'These totals do not add up.'));
    warning.appendChild(el('p', null,
      'The buckets sum to ' + check.sum + ' but the candidate set holds ' +
      check.candidate_set + '. A standard has no outcome row, so do not quote ' +
      'any number on this screen until that is fixed.'));
    return warning;
  }

  function render(ctx) {
    if (!ctx.run) { return; }

    queueItems = ctx.queue.items || [];

    mount.innerHTML = '';
    mount.appendChild(heading(ctx));
    mount.appendChild(tiles(ctx));
    mount.appendChild(percentages(ctx));

    var problem = countCheckWarning(ctx);
    if (problem) { mount.appendChild(problem); }
  }

  /* Called by queue.js after a decision, so the "Needs your check" tile counts
   * down as the reviewer works. Only that tile changes, so nothing else on the
   * panel is rebuilt and no focus is disturbed. */
  function refresh() {
    var value = mount.querySelector('.wb-tile-attention .wb-tile-value');
    if (value) { value.textContent = String(standardsPending()); }
  }

  return {
    render: render,
    refresh: refresh,
    showMessage: showMessage
  };
})();
