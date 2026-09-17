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

  // ---- Naming a lesson, and deciding what still needs a person -----------

  /* "4.6" — unit and lesson, the way the mockup showed it and the way the
   * team says it out loud.
   *
   * The unit number is `displayed_number` and nothing else. `position` is the
   * unit's order in the course and the two are different things: the contract
   * is explicit that you show one and sort by the other, never compute either
   * from the other. Most AIF units carry no displayed_number at all, so for
   * those this is the lesson token alone rather than a unit number invented
   * from the ordering. A wrong "6.11" would look exactly as authoritative as
   * a right one. */
  function unitLessonLabel(lesson) {
    var unit = lesson.displayed_number;
    if (unit === null || unit === undefined || unit === '') {
      return String(lesson.lesson_token);
    }
    return unit + '.' + lesson.lesson_token;
  }

  /* The unit in words, always shown: a lesson token on its own does not say
   * where in the course you are. */
  function unitLabel(lesson) {
    return lesson.displayed_number
      ? 'Unit ' + lesson.displayed_number + ' — ' + lesson.unit_name
      : lesson.unit_name;
  }

  /* Still a person's to answer. A decision made in this session settles it
   * whatever the store last said; otherwise the store's status decides.
   * `stale` counts as needing review — it was accepted once and the lesson
   * has changed underneath it since. */
  function recordNeedsReview(record) {
    if (D.get(record.id)) { return false; }
    return record.review_status === 'proposed' || record.review_status === 'stale';
  }

  function settledWord(record) {
    var decision = D.get(record.id);
    var status = decision ? decision.review_status : record.review_status;
    return status === 'accepted' ? 'accepted'
         : status === 'rejected' ? 'rejected'
         : status;
  }

  // ---- Filtering --------------------------------------------------------

  function recordsOf(item) {
    return item.records || [];
  }

  function itemHasPending(item) {
    return recordsOf(item).some(recordNeedsReview);
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

    var cancelBtn = el('button', 'quiet', 'Cancel');
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

    var head = el('div', 'wb-record-head');
    head.appendChild(el('span', 'wb-pill wb-pill-lesson', unitLessonLabel(lesson)));
    head.appendChild(el('span', 'wb-record-title', lesson.lesson_name));
    li.appendChild(head);

    /* Where this lesson sits. A lesson name alone does not tell a reviewer
     * which unit they are in, and every one of these cards used to read the
     * same without it. */
    li.appendChild(el('p', 'wb-record-where',
      unitLabel(lesson) + ' · proposed at ' + record.level));

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

    var rejectBtn = el('button', 'quiet', 'Reject');
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

    var pending = records.filter(recordNeedsReview);

    if (!pending.length) {
      wrap.appendChild(el('p', 'wb-all-settled',
        'Every match on this standard has been reviewed.'));
      return wrap;
    }

    var ul = el('ul', 'wb-record-list');
    pending.forEach(function (record) {
      ul.appendChild(evidenceItem(standard, record));
    });
    wrap.appendChild(ul);

    return wrap;
  }

  /* Matches that no longer need a person, as pills beside the standard.
   *
   * They still matter — they are part of the picture for this standard — but
   * a settled match does not need a whole card with evidence, a depth picker
   * and two buttons. As a pill it takes one line, and what is left below is
   * only the work. The word is in the pill, not just a colour. */
  function settledPills(records) {
    var settled = records.filter(function (record) {
      return !recordNeedsReview(record);
    });
    if (!settled.length) { return null; }

    var wrap = el('div', 'wb-settled');
    wrap.appendChild(el('span', 'wb-settled-label',
      settled.length === 1 ? 'Reviewed:' : 'Reviewed (' + settled.length + '):'));

    settled.forEach(function (record) {
      var word = settledWord(record);
      var pill = el('span',
        'wb-pill ' + (word === 'rejected' ? 'wb-pill-rejected' : 'wb-pill-done'),
        unitLessonLabel(record.lesson) + ' ' + word);
      pill.title = record.lesson.lesson_name + ' — ' + unitLabel(record.lesson);
      wrap.appendChild(pill);
    });

    return wrap;
  }

  function standardCard(item, position, total) {
    var standard = item.standard;
    var li = el('li', 'wb-card');
    li.id = 'card-' + standard.id;

    /* Everything a reviewer needs to keep in view while they read the
     * evidence below: which standard this is, what it says, and which of its
     * matches are already settled. It sticks to the top of the viewport for
     * as long as the card is on screen.
     *
     * The boundary notes are deliberately NOT in here. Opened, they are tall
     * enough to pin half the screen, and they are a thing you consult once
     * rather than something to hold in view. */
    var top = el('div', 'wb-card-sticky');

    var head = el('div', 'wb-card-head');

    var heading = el('h4', 'wb-ident', standard.identifier);
    heading.id = 'standard-' + standard.id;
    heading.tabIndex = -1;
    head.appendChild(heading);

    if (standard.concept) {
      head.appendChild(el('span', 'wb-pill wb-pill-concept', standard.concept));
    }

    head.appendChild(el('span', 'wb-position', position + ' of ' + total));
    top.appendChild(head);

    top.appendChild(el('p', 'wb-statement', standard.statement));

    var settled = settledPills(recordsOf(item));
    if (settled) { top.appendChild(settled); }

    li.appendChild(top);

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

    focusAfter(fresh, focusRecordId);
  }

  /* Where the keyboard goes after a card is repainted.
   *
   * A decided record no longer has a card — it moves up to the settled pills —
   * so the status line this used to focus is gone by the time we look for it.
   * Landing on <body> there would drop a reviewer to the top of a 55-standard
   * page on every Accept, which is the exact failure the per-card repaint
   * exists to avoid. So: the reason box if a rejection is open, the record's
   * own status line if it is still on screen, otherwise the next thing in
   * this card worth acting on, and the standard's heading as a last resort. */
  function focusAfter(card, recordId) {
    var target = rejecting[recordId]
      ? document.getElementById('reason-' + recordId)
      : document.getElementById('status-' + recordId);

    if (!target) {
      target = card.querySelector('button[id^="accept-"]') ||
               card.querySelector('.wb-ident');
    }
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

  /* A run's worth of state, thrown away when a different run arrives. Left
   * behind, a half-open rejection box or a concept filter from the previous
   * run would apply itself to standards that never had either. */
  function reset() {
    items = [];
    conceptFilter = '';
    onlyPending = false;
    rejecting = {};
    reasonErrors = {};
    cardNodes = {};
    announce('');
  }

  function render(ctx) {
    if (!ctx.run) { return; }

    reset();
    items = ctx.queue.items || [];

    if (!items.length) {
      controls.hidden = true;
      say('The queue is empty. Nothing from this run is waiting on a person.');
      return;
    }

    renderControls();
    renderList();

    /* The envelope carries a cursor and the service has never set it — it
     * returns the whole run in one response. If that ever changes, a page
     * that ignores it would quietly show a fraction of the queue and look
     * complete. Cheaper to say so than to find out from a wrong total. */
    if (ctx.queue.cursor) {
      var more = el('p', 'wb-note',
        'The service says there is more of this queue than it sent. This ' +
        'page shows only what arrived, so the counts above are low.');
      more.setAttribute('role', 'alert');
      mount.appendChild(more);
    }
  }

  function showMessage(text) {
    controls.hidden = true;
    say(text);
  }

  return {
    render: render,
    showMessage: showMessage
  };
})();
