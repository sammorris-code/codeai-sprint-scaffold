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
 * The one rule this file exists to keep honest: a run reaches a district when
 * a person approves it, and never for any other reason. An earlier version of
 * this screen said a run was held back until every boundary note in the set
 * had been checked. That rule is gone - contract/REVIEW-DESIGN.md says why -
 * and the banner here states the real one. loader.js's runStatus() decides it;
 * this file only prints what it returns.
 */

window.RunSummary = (function () {
  'use strict';

  var S = window.StandardsSource;
  var D = window.ReviewDecisions;

  var mount = document.getElementById('run-summary');
  var totalRecords = 0;

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

  function pendingRecords() {
    return Math.max(0, totalRecords - D.count());
  }

  function countRecords(queue) {
    return (queue.items || []).reduce(function (sum, item) {
      return sum + (item.records ? item.records.length : 0);
    }, 0);
  }

  /* The grades this run covers.
   *
   * Taken from the standards themselves, not from the set: a set's `scope` is
   * free text somebody may or may not have filled in - it is null on the
   * Oklahoma set - while grade_band is on every standard by the time one has
   * been ingested. The set's scope is the fallback, and saying nothing is
   * better than guessing. */
  function gradeLabel(ctx) {
    var seen = {};
    (ctx.queue.items || []).forEach(function (item) {
      var band = item.standard && item.standard.grade_band;
      if (band) { seen[band] = true; }
    });

    var bands = Object.keys(seen).sort();
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
      ctx.course ? ctx.course.course_name : null
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
    wrap.appendChild(tile('Needs your check', pendingRecords(), 'attention'));
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

    wrap.appendChild(el('p', 'wb-percent-line',
      coverage.in_scope.percent + '% of the standards in scope are covered (' +
      coverage.in_scope.covered + ' of ' + coverage.in_scope.total + '). ' +
      'Across the whole framework it is ' + coverage.whole_framework.percent +
      '% (' + coverage.whole_framework.covered + ' of ' +
      coverage.whole_framework.total + ').'));

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

  /* The release gate, and the only place this screen speaks about publishing. */
  function publishBanner(ctx) {
    var state = S.runStatus(ctx.run);
    var banner = el('div', 'wb-banner ' +
      (state.published ? 'wb-banner-published' : 'wb-banner-holding'));
    banner.setAttribute('role', 'status');

    banner.appendChild(el('p', 'wb-banner-title',
      state.published ? 'Published' : 'Not published yet'));
    banner.appendChild(el('p', null, state.text));

    /* Said here on purpose. This is exactly where the old screen claimed the
     * boundary notes held the release, so this is where a reviewer who
     * remembers that needs to be told they do not. */
    if (ctx.set && !ctx.set.all_boundaries_checked) {
      banner.appendChild(el('p', 'wb-banner-aside',
        'The boundary notes for this set are still drafts. That does not hold ' +
        'anything back — a note gets checked when an alignment turns on it.'));
    }

    return banner;
  }

  function render(ctx) {
    if (!ctx.run) { return; }

    totalRecords = countRecords(ctx.queue);

    mount.innerHTML = '';
    mount.appendChild(heading(ctx));
    mount.appendChild(tiles(ctx));
    mount.appendChild(percentages(ctx));

    var problem = countCheckWarning(ctx);
    if (problem) { mount.appendChild(problem); }

    mount.appendChild(publishBanner(ctx));
  }

  /* Called by queue.js after a decision, so the "Needs your check" tile counts
   * down as the reviewer works. Only that tile changes, so nothing else on the
   * panel is rebuilt and no focus is disturbed. */
  function refresh() {
    var value = mount.querySelector('.wb-tile-attention .wb-tile-value');
    if (value) { value.textContent = String(pendingRecords()); }
  }

  return {
    render: render,
    refresh: refresh,
    showMessage: showMessage
  };
})();
