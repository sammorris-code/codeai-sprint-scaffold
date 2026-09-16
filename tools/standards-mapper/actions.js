/* actions.js — what a reviewer does with a queue once they have worked it.
 *
 * Save the decisions, and compare this run to the one before it. Both sit
 * below the queue because both are things you reach for at the end.
 *
 * Saving belongs to decisions-store.js; this file only puts buttons on it.
 */

window.QueueActions = (function () {
  'use strict';

  var S = window.StandardsSource;
  var D = window.ReviewDecisions;

  var mount = document.getElementById('queue-actions');
  var context = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function button(text, onClick, className) {
    var b = el('button', className || null, text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  /* Saving nothing produces an empty file, which looks like the tool broke
   * rather than like there was nothing to save. Say which it is. */
  function guardEmpty(save) {
    return function () {
      if (!D.count()) {
        report('No decisions to save yet. Accept or reject something first.');
        return;
      }
      save();
      report(D.count() + ' decision' + (D.count() === 1 ? '' : 's') + ' saved.');
    };
  }

  function report(message) {
    var line = document.getElementById('actions-status');
    if (line) { line.textContent = message; }
  }

  // ---- Compare to last run ---------------------------------------------

  function diffLine(entry) {
    return entry.standard_identifier + ' — ' + entry.lesson_name;
  }

  function diffGroup(heading, entries) {
    if (!entries || !entries.length) { return null; }

    var wrap = el('div', 'wb-diff-group');
    wrap.appendChild(el('p', 'wb-diff-head',
      heading + ' (' + entries.length + ')'));

    var ul = document.createElement('ul');
    entries.forEach(function (entry) {
      ul.appendChild(el('li', null, diffLine(entry)));
    });
    wrap.appendChild(ul);
    return wrap;
  }

  function renderDiff(diff) {
    var panel = document.getElementById('run-diff');
    panel.innerHTML = '';

    panel.appendChild(el('h4', null,
      'Compared with run ' + diff.against_run_id +
      ' (course version ' + diff.snapshot_from + ' to ' + diff.snapshot_to + ')'));

    var groups = [
      diffGroup('Accepted before, and the lesson has changed since', diff.stale),
      diffGroup('New since that run', diff.added),
      diffGroup('Gone since that run', diff.removed),
      diffGroup('Proposed at a different depth', diff.level_changed)
    ].filter(Boolean);

    if (!groups.length) {
      panel.appendChild(el('p', null, 'Nothing changed between these two runs.'));
      return;
    }

    groups.forEach(function (group) { panel.appendChild(group); });
  }

  function compare() {
    var panel = document.getElementById('run-diff');
    panel.textContent = 'Reading the comparison…';

    S.load('run-diff')
      .then(renderDiff)
      .catch(function (error) {
        panel.textContent = 'The comparison could not be read. ' + error.message;
      });
  }

  /* The contract types previous_run_id as integer-or-null, so "no previous
   * run" is null and nothing else. Testing it for truthiness would read a
   * real run 0 as absent and quietly disable the comparison against it. */
  function hasPreviousRun(run) {
    return run.previous_run_id !== null && run.previous_run_id !== undefined;
  }

  // ---- The row ----------------------------------------------------------

  function render(ctx) {
    context = ctx;
    mount.innerHTML = '';

    var row = el('div', 'actions');
    row.appendChild(button('Download decisions', guardEmpty(D.save)));
    row.appendChild(button('Save as CSV', guardEmpty(D.saveCsv), 'quiet'));

    /* The first run against a set has nothing behind it. A button that looks
     * available and then reports "nothing to compare" wastes the click; one
     * that is off with the reason beside it does not. */
    var compareBtn = button('Compare to last run', compare, 'quiet');
    compareBtn.disabled = !hasPreviousRun(ctx.run);
    row.appendChild(compareBtn);

    mount.appendChild(row);

    if (!hasPreviousRun(ctx.run)) {
      mount.appendChild(el('p', 'wb-note',
        'This is the first run against this set, so there is nothing to ' +
        'compare it with yet.'));
    }

    var status = el('p', 'wb-note');
    status.id = 'actions-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    mount.appendChild(status);

    var diffPanel = el('div', 'wb-diff');
    diffPanel.id = 'run-diff';
    mount.appendChild(diffPanel);
  }

  function hide(message) {
    mount.innerHTML = '';
    mount.appendChild(el('p', 'wb-note', message));
  }

  function needsServing() {
    hide('Saving and comparing need this page to be served.');
  }

  function showError(error) {
    hide('These actions are unavailable: the run could not be read. ' +
         error.message);
  }

  return {
    render: render,
    needsServing: needsServing,
    showError: showError
  };
})();
