/* run-summary.js — what this run is, and where it stands.
 *
 * The four tiles, the publish banner and the scope note at the top of the
 * workbench. Reads the context workbench.js builds; owns no fetching.
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
  var context = null;
  var totalRecords = 0;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function say(message) {
    mount.innerHTML = '';
    mount.appendChild(el('p', 'wb-note', message));
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

  /* The run, named the way a person would say it out loud. */
  function heading(ctx) {
    var wrap = el('div', 'wb-run-head');

    var title = el('h3', 'wb-run-title',
      ctx.set ? ctx.set.title : 'Standards set ' + ctx.run.set_id);
    wrap.appendChild(title);

    var parts = [];
    if (ctx.set) { parts.push(S.setLabel(ctx.set)); }
    if (ctx.course) { parts.push(ctx.course.course_name); }
    parts.push('by ' + ctx.run.grain);
    parts.push('course version ' + ctx.run.snapshot_id);
    wrap.appendChild(el('p', 'wb-run-detail', parts.join(' · ')));

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
    context = ctx;
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
    if (!context) { return; }
    var value = mount.querySelector('.wb-tile-attention .wb-tile-value');
    if (value) { value.textContent = String(pendingRecords()); }
  }

  function needsServing() {
    say('The run summary needs this page to be served before it can load.');
  }

  function showError(error) {
    say('The run summary could not be read. ' + error.message);
  }

  return {
    render: render,
    refresh: refresh,
    needsServing: needsServing,
    showError: showError
  };
})();
