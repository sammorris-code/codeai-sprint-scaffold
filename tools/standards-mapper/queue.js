/* queue.js — the review queue, as a list of standard cards.
 *
 * One card per standard: what it says, what counts as teaching it and what
 * does not, then each lesson proposed as evidence with a depth control and
 * Accept/Reject beside it.
 *
 * Two things about this file are deliberate and worth keeping.
 *
 * 1. Where a decision goes once made is decisions-store.js's job. This file
 *    only ever calls window.ReviewDecisions.
 *
 * 2. A decision rebuilds ONE card, not the whole list. Rebuilding everything
 *    would drop keyboard focus back to <body> on every Accept, which on a
 *    forty-standard queue means losing your place forty times. replaceCard()
 *    swaps a single <li> and puts focus back where the reviewer left it.
 *
 * What this file no longer does: hold back publishing until the set's
 * boundary notes were checked. That rule is gone (contract/REVIEW-DESIGN.md)
 * and publishing now belongs to the run, not to this queue - run-summary.js
 * states it.
 */

window.ReviewQueue = (function () {
  'use strict';

  var D = window.ReviewDecisions;

  var mount = document.getElementById('queue-list');
  var controls = document.getElementById('queue-controls');
  var announcer = document.getElementById('queue-announcer');

  var LEVELS = ['introduced', 'developed', 'mastered'];

  var items = [];
  var conceptFilter = '';
  var onlyPending = false;

  // record id -> true while that record's reject reason field is open.
  var rejecting = {};

  // record id -> a validation message for that record's reason field.
  var reasonErrors = {};

  // standard id -> the <li> currently on screen for it.
  var cardNodes = {};

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

  function announce(message) {
    announcer.textContent = message;
  }

  // ---- Filtering --------------------------------------------------------

  function recordsOf(item) {
    return item.records || [];
  }

  function itemHasPending(item) {
    return recordsOf(item).some(function (record) {
      return !D.get(record.id);
    });
  }

  function visibleItems() {
    return items.filter(function (item) {
      if (conceptFilter && item.standard.concept !== conceptFilter) {
        return false;
      }
      if (onlyPending && !itemHasPending(item)) {
        return false;
      }
      return true;
    });
  }

  function concepts() {
    var seen = {};
    items.forEach(function (item) {
      if (item.standard.concept) { seen[item.standard.concept] = true; }
    });
    return Object.keys(seen).sort();
  }

  /* The filter row. Built here rather than written into index.html because
   * the concept list comes from the run: a set with no Networks standards
   * should not offer to filter by Networks. */
  function renderControls() {
    controls.innerHTML = '';

    var conceptField = el('p', 'field');
    var conceptLabel = el('label', null, 'Show');
    conceptLabel.setAttribute('for', 'concept-filter');
    conceptField.appendChild(conceptLabel);

    var select = document.createElement('select');
    select.id = 'concept-filter';

    var all = document.createElement('option');
    all.value = '';
    all.textContent = 'All concepts';
    select.appendChild(all);

    concepts().forEach(function (concept) {
      var option = document.createElement('option');
      option.value = concept;
      option.textContent = concept;
      select.appendChild(option);
    });

    select.value = conceptFilter;
    select.addEventListener('change', function () {
      conceptFilter = select.value;
      renderList();
      announceCount();
    });
    conceptField.appendChild(select);
    controls.appendChild(conceptField);

    var checkField = el('p', 'check');
    var checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = 'only-pending';
    checkbox.checked = onlyPending;
    checkbox.addEventListener('change', function () {
      onlyPending = checkbox.checked;
      renderList();
      announceCount();
    });
    checkField.appendChild(checkbox);

    var checkLabel = el('label', null, 'Only standards still needing a decision');
    checkLabel.setAttribute('for', 'only-pending');
    checkField.appendChild(checkLabel);
    controls.appendChild(checkField);

    controls.hidden = false;
  }

  function announceCount() {
    var shown = visibleItems().length;
    announce(shown + ' of ' + items.length + ' standards shown.');
  }

  // ---- Pieces of a card -------------------------------------------------

  function boundaryList(heading, entries) {
    var wrap = el('div', 'wb-boundary');
    wrap.appendChild(el('p', 'wb-boundary-head', heading));

    if (!entries || !entries.length) {
      wrap.appendChild(el('p', null, 'None written yet.'));
      return wrap;
    }

    var ul = el('ul', 'wb-boundary-list');
    entries.forEach(function (entry) {
      ul.appendChild(el('li', null, entry));
    });
    wrap.appendChild(ul);

    return wrap;
  }

  /* A choice-level record is capped at "introduced" by the contract itself
   * (only some students ever see it) — so there is no picker to change it,
   * only a plain statement of the cap. Letting a reviewer pick "mastered"
   * here would let a partial activity count as full coverage. */
  function levelSelectFor(record, decision) {
    if (record.is_choice_level) {
      var fixed = el('span', 'wb-level-fixed',
        'introduced (capped — this evidence is optional)');
      fixed.id = 'level-' + record.id;
      return fixed;
    }

    var select = document.createElement('select');
    select.id = 'level-' + record.id;

    LEVELS.forEach(function (level) {
      var option = document.createElement('option');
      option.value = level;
      option.textContent = level;
      select.appendChild(option);
    });

    select.value = (decision && decision.chosen_level) || record.level;
    return select;
  }

  /* Warnings, in the words the data gives them — never the internal "kind"
   * (e.g. "weak_match"). The label is what a reviewer should read; the kind
   * is just how the system files it.
   *
   * A warning is a pill so it is visible at a glance, and its text carries
   * the meaning on its own: colour alone would not reach a reviewer who
   * cannot distinguish these two, and there are only ever two. */
  function warningPills(flags) {
    var wrap = el('div', 'wb-pills');

    (flags || []).forEach(function (flag) {
      var pill = el('span', 'wb-pill wb-pill-warn', flag.label);
      if (flag.detail) { pill.title = flag.detail; }
      wrap.appendChild(pill);
    });

    return wrap;
  }

  /* The pill above already says which warning this is, so a single detail
   * line does not repeat the label. With two warnings on one record it has
   * to, or there is no telling which detail belongs to which pill. */
  function warningDetails(flags) {
    var wrap = el('div', 'wb-warning-detail');
    var withDetail = (flags || []).filter(function (flag) { return flag.detail; });

    withDetail.forEach(function (flag) {
      wrap.appendChild(el('p', null, withDetail.length > 1
        ? flag.label + ' — ' + flag.detail
        : flag.detail));
    });

    return wrap;
  }

  function reasonFieldFor(record, standard, getLevel) {
    var wrap = el('div', 'wb-reason');

    var reasonId = 'reason-' + record.id;
    var label = el('label', null, 'Reason for rejecting');
    label.setAttribute('for', reasonId);
    wrap.appendChild(label);

    var input = document.createElement('input');
    input.type = 'text';
    input.id = reasonId;
    wrap.appendChild(input);

    if (reasonErrors[record.id]) {
      var errorId = 'reason-error-' + record.id;
      var error = el('p', 'wb-error', reasonErrors[record.id]);
      error.id = errorId;
      wrap.appendChild(error);
      input.setAttribute('aria-describedby', errorId);
      input.setAttribute('aria-invalid', 'true');
    }

    var buttons = el('div', 'wb-record-actions');

    var confirmBtn = el('button', null, 'Confirm rejection');
    confirmBtn.type = 'button';
    confirmBtn.addEventListener('click', function () {
      var reason = input.value.trim();
      if (!reason) {
        reasonErrors[record.id] = 'A reason is required.';
        replaceCard(standard.id, record.id);
        return;
      }
      delete reasonErrors[record.id];
      delete rejecting[record.id];
      decide(standard, record, {
        review_status: 'rejected',
        level: null,
        chosen_level: getLevel(),
        reason: reason
      });
    });
    buttons.appendChild(confirmBtn);

    var cancelBtn = el('button', null, 'Cancel');
    cancelBtn.type = 'button';
    cancelBtn.addEventListener('click', function () {
      delete rejecting[record.id];
      delete reasonErrors[record.id];
      replaceCard(standard.id, record.id);
    });
    buttons.appendChild(cancelBtn);

    wrap.appendChild(buttons);
    return wrap;
  }

  /* Writes the decision, then repaints just this card.
   *
   * standard_identifier and lesson_name go in alongside the ids because the
   * CSV a reviewer hands to somebody else has to be readable without this
   * tool open. The service only ever needs record_id. */
  function decide(standard, record, decision) {
    decision.record_id = record.id;
    decision.standard_identifier = standard.identifier;
    decision.lesson_name = record.lesson.lesson_name;
    D.set(record.id, decision);

    replaceCard(standard.id, record.id);

    if (window.RunSummary && window.RunSummary.refresh) {
      window.RunSummary.refresh();
    }

    announce(standard.identifier + ', ' + record.lesson.lesson_name + ': ' +
      (decision.review_status === 'accepted'
        ? 'accepted at ' + decision.chosen_level + '.'
        : 'rejected.') +
      ' ' + D.count() + ' of ' + totalRecords() + ' lessons reviewed.');
  }

  function totalRecords() {
    return items.reduce(function (sum, item) {
      return sum + recordsOf(item).length;
    }, 0);
  }

  function evidenceItem(standard, record) {
    var lesson = record.lesson;
    var decision = D.get(record.id);
    var li = el('li', 'wb-record');

    var unitLabel = lesson.displayed_number
      ? 'Unit ' + lesson.displayed_number + ' — ' + lesson.unit_name
      : lesson.unit_name;

    var head = el('div', 'wb-record-head');
    head.appendChild(el('span', 'wb-pill wb-pill-lesson', lesson.lesson_token));
    head.appendChild(el('span', 'wb-record-title',
      lesson.lesson_name + ' (' + unitLabel + ') — proposed at ' + record.level));
    li.appendChild(head);

    /* Stale is the most important thing on the screen: this was already
     * accepted, and the lesson has since changed underneath it. It must say
     * that plainly, regardless of whatever fresh decision gets made below. */
    if (record.review_status === 'stale') {
      /* Deliberately not role="alert". These cards are on the page from the
       * moment it loads, and an alert role fires the instant its node is
       * inserted - so a queue with six stale records would shout six times
       * over each other before the reviewer had read anything. The words
       * carry it instead, and they lead with what to do. */
      li.appendChild(el('p', 'wb-stale',
        'Needs review again: this was accepted before, and the lesson has ' +
        'changed since.'));
    }

    li.appendChild(warningPills(record.flags));
    li.appendChild(warningDetails(record.flags));

    li.appendChild(el('p', 'wb-objective',
      lesson.has_objectives && lesson.objectives && lesson.objectives.length
        ? 'Objective: ' + lesson.objectives.join(' ')
        : 'No stated objective.'));

    li.appendChild(el('p', 'wb-proof', 'Proof: ' + record.evidence));

    if (record.note) {
      li.appendChild(el('p', 'wb-record-note', 'Note: ' + record.note));
    }

    var levelLabel = el(record.is_choice_level ? 'p' : 'label', 'wb-level');
    if (!record.is_choice_level) {
      levelLabel.setAttribute('for', 'level-' + record.id);
    }
    levelLabel.appendChild(document.createTextNode('Depth: '));
    var levelSelect = levelSelectFor(record, decision);
    levelLabel.appendChild(levelSelect);
    li.appendChild(levelLabel);

    // A <select> has .value; the fixed choice-level display does not.
    function currentLevel() {
      return record.is_choice_level ? record.level : levelSelect.value;
    }

    if (record.is_choice_level) {
      li.appendChild(el('p', 'wb-record-note',
        'Optional evidence: only ' + record.choice_option +
        ' does this. Cannot count as full coverage.'));
    }

    if (rejecting[record.id]) {
      li.appendChild(reasonFieldFor(record, standard, currentLevel));
      return li;
    }

    var actions = el('div', 'wb-record-actions');

    /* Every card carries an Accept and a Reject, so "Accept" on its own is
     * ambiguous to anyone moving through the page by button. The visible word
     * stays short; the accessible name says which lesson it acts on. */
    var acceptBtn = el('button', null, 'Accept');
    acceptBtn.id = 'accept-' + record.id;
    acceptBtn.type = 'button';
    acceptBtn.setAttribute('aria-label',
      'Accept ' + lesson.lesson_name + ' for ' + standard.identifier);
    acceptBtn.addEventListener('click', function () {
      var chosen = currentLevel();
      decide(standard, record, {
        review_status: 'accepted',
        level: chosen === record.level ? null : chosen,
        chosen_level: chosen,
        reason: null
      });
    });
    actions.appendChild(acceptBtn);

    var rejectBtn = el('button', null, 'Reject');
    rejectBtn.id = 'reject-' + record.id;
    rejectBtn.type = 'button';
    rejectBtn.setAttribute('aria-label',
      'Reject ' + lesson.lesson_name + ' for ' + standard.identifier);
    rejectBtn.addEventListener('click', function () {
      rejecting[record.id] = true;
      replaceCard(standard.id, record.id);
    });
    actions.appendChild(rejectBtn);

    li.appendChild(actions);

    var status = el('p', 'wb-record-status');
    status.id = 'status-' + record.id;
    status.tabIndex = -1;
    if (decision && decision.review_status === 'accepted') {
      status.textContent = 'Accepted at ' + decision.chosen_level + '.';
    } else if (decision && decision.review_status === 'rejected') {
      status.textContent = 'Rejected: ' + decision.reason;
    } else {
      status.textContent = 'Not yet reviewed.';
    }
    li.appendChild(status);

    return li;
  }

  /* "No evidence" is not one thing. A heading, an out-of-scope standard, a
   * requirement no curriculum could meet, evidence rejected against the
   * boundary, and an actual gap all arrive with zero records — and read as
   * an identical, alarming blank unless something here tells them apart. */
  function noEvidenceLabel(standard, outcome) {
    if (standard.hierarchy_role === 'umbrella') {
      return 'Heading — not a standard on its own';
    }
    if (outcome && outcome.in_scope === false) {
      return 'Out of scope';
    }
    if (outcome && outcome.outcome === 'not_curriculum_addressable') {
      return 'Not something curriculum can address';
    }
    if (outcome && outcome.outcome === 'boundary_issue') {
      return 'Evidence rejected against the boundary';
    }
    return 'Gap';
  }

  function evidenceList(standard, outcome, records) {
    var wrap = el('div', 'wb-evidence');
    wrap.appendChild(el('p', 'wb-evidence-head', 'Proposed evidence'));

    if (!records || !records.length) {
      var empty = el('div', 'wb-no-evidence');
      empty.appendChild(el('p', 'wb-no-evidence-label',
        noEvidenceLabel(standard, outcome)));
      empty.appendChild(el('p', null,
        (outcome && outcome.rationale) || 'No evidence proposed.'));
      wrap.appendChild(empty);
      return wrap;
    }

    var ul = el('ul', 'wb-record-list');
    records.forEach(function (record) {
      ul.appendChild(evidenceItem(standard, record));
    });
    wrap.appendChild(ul);

    return wrap;
  }

  function standardCard(item, position, total) {
    var standard = item.standard;
    var li = el('li', 'wb-card');
    li.id = 'card-' + standard.id;

    var head = el('div', 'wb-card-head');

    var heading = el('h4', 'wb-ident', standard.identifier);
    heading.id = 'standard-' + standard.id;
    heading.tabIndex = -1;
    head.appendChild(heading);

    if (standard.concept) {
      head.appendChild(el('span', 'wb-pill wb-pill-concept', standard.concept));
    }
    if (!itemHasPending(item) && recordsOf(item).length) {
      head.appendChild(el('span', 'wb-pill wb-pill-done', 'Reviewed'));
    }

    head.appendChild(el('span', 'wb-position', position + ' of ' + total));
    li.appendChild(head);

    li.appendChild(el('p', 'wb-statement', standard.statement));

    /* <details> rather than a panel that is always open: the boundary notes
     * matter when a match looks wrong, and are noise the rest of the time.
     * A real <details> is keyboard-operable for free. */
    var boundaries = document.createElement('details');
    boundaries.className = 'wb-boundaries';
    var summary = document.createElement('summary');
    summary.textContent = 'What counts as teaching this standard';
    boundaries.appendChild(summary);
    boundaries.appendChild(boundaryList('Counts as teaching it', standard.boundary_includes));
    boundaries.appendChild(boundaryList('Does not count', standard.boundary_excludes));

    if (standard.boundary_provenance === 'drafted') {
      boundaries.appendChild(el('p', 'wb-drafted-note',
        'These notes are a draft nobody has checked. If a match below was ' +
        'rejected against them, the notes may be what is wrong, not the lesson.'));
    }
    li.appendChild(boundaries);

    li.appendChild(evidenceList(standard, item.outcome, item.records));

    cardNodes[standard.id] = li;
    return li;
  }

  /* Repaints one card in place and puts focus back inside it.
   *
   * focusRecordId names the record the reviewer was acting on. Where focus
   * lands depends on what the card now shows: the reason box if rejection is
   * open, the decision line if a decision was just made, the Accept button if
   * the decision was cancelled. */
  function replaceCard(standardId, focusRecordId) {
    var old = cardNodes[standardId];
    if (!old || !old.parentNode) { return; }

    var shown = visibleItems();
    var position = 0;
    var item = null;

    shown.forEach(function (candidate, offset) {
      if (candidate.standard.id === standardId) {
        item = candidate;
        position = offset + 1;
      }
    });

    /* The card may have just been filtered out of the list by its own
     * decision — "only standards still needing a decision" is on and this was
     * the last pending record. Drop it and move focus somewhere real rather
     * than leaving it on a node that is no longer in the page. */
    if (!item) {
      var parent = old.parentNode;
      old.parentNode.removeChild(old);
      delete cardNodes[standardId];
      renumber();
      var firstHeading = parent.querySelector('.wb-ident');
      if (firstHeading) {
        firstHeading.focus();
      } else {
        renderList();
      }
      return;
    }

    var fresh = standardCard(item, position, shown.length);
    old.parentNode.replaceChild(fresh, old);

    var target = rejecting[focusRecordId]
      ? document.getElementById('reason-' + focusRecordId)
      : (D.get(focusRecordId)
        ? document.getElementById('status-' + focusRecordId)
        : document.getElementById('accept-' + focusRecordId));
    if (target) { target.focus(); }
  }

  /* Positions are "3 of 12" against what is on screen, so removing a card
   * has to renumber the ones left rather than leave a gap in the count. */
  function renumber() {
    var positions = mount.querySelectorAll('.wb-position');
    for (var i = 0; i < positions.length; i += 1) {
      positions[i].textContent = (i + 1) + ' of ' + positions.length;
    }
  }

  function renderList() {
    var shown = visibleItems();
    cardNodes = {};
    mount.innerHTML = '';

    if (!shown.length) {
      mount.appendChild(el('p', 'wb-note',
        items.length
          ? 'Nothing matches this filter. Every standard here has been reviewed, ' +
            'or belongs to another concept.'
          : 'The queue is empty.'));
      return;
    }

    var ul = el('ul', 'wb-card-list');
    shown.forEach(function (item, offset) {
      ul.appendChild(standardCard(item, offset + 1, shown.length));
    });
    mount.appendChild(ul);
  }

  function render(ctx) {
    items = ctx.queue.items || [];

    if (!items.length) {
      controls.hidden = true;
      say('The queue is empty. Nothing from this run is waiting on a person.');
      return;
    }

    renderControls();
    renderList();
  }

  function needsServing() {
    controls.hidden = true;
    say('This page needs to be served before it can read the review queue.');
  }

  function showError(error) {
    controls.hidden = true;
    say('The review queue could not be read. ' + error.message);
  }

  return {
    render: render,
    needsServing: needsServing,
    showError: showError
  };
})();
