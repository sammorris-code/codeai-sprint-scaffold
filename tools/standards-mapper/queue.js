/* queue.js — Step 3: Accept, Reject, and a decisions file.
 *
 * Loads the review-queue fixture through loader.js and shows one standard at
 * a time: its statement, the boundary notes, then the lessons proposed as
 * evidence. Each proposed lesson gets a depth control and Accept/Reject.
 *
 * Where a decision goes once made is decisions-store.js's job, not this
 * file's. This file only ever calls window.ReviewDecisions.
 */

(function () {
  'use strict';

  var S = window.StandardsSource;
  var D = window.ReviewDecisions;
  var mount = document.getElementById('queue-list');
  var announcer = document.getElementById('queue-announcer');

  var LEVELS = ['introduced', 'developed', 'mastered'];

  var items = [];
  var index = 0;
  var totalRecords = 0;
  var currentSet = null;

  // record id -> true while that record's reject reason field is open.
  var rejecting = {};

  // record id -> a validation message for that record's reason field.
  var reasonErrors = {};

  /* render() replaces the whole standard's markup, which would otherwise
   * drop keyboard focus back to <body> every time. These two flags tell the
   * next render where focus belongs afterward, so nobody using a keyboard
   * ever loses their place. Only one is ever set at a time — moving between
   * standards and acting on a record never happen in the same click. */
  var focusStandardOnRender = false;
  var focusRecordOnRender = null;

  function setDecision(recordId, decision) {
    D.set(recordId, decision);
    render();
  }

  function say(message) {
    mount.textContent = message;
  }

  function boundaryList(heading, entries) {
    var wrap = document.createElement('div');

    var h = document.createElement('p');
    h.textContent = heading;
    wrap.appendChild(h);

    if (!entries || !entries.length) {
      var none = document.createElement('p');
      none.textContent = 'None written yet.';
      wrap.appendChild(none);
      return wrap;
    }

    var ul = document.createElement('ul');
    entries.forEach(function (entry) {
      var li = document.createElement('li');
      li.textContent = entry;
      ul.appendChild(li);
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
      var fixed = document.createElement('span');
      fixed.id = 'level-' + record.id;
      fixed.textContent = 'introduced (capped — this evidence is optional)';
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

  function reasonFieldFor(record, getLevel) {
    var wrap = document.createElement('div');

    var reasonId = 'reason-' + record.id;
    var label = document.createElement('label');
    label.setAttribute('for', reasonId);
    label.textContent = 'Reason for rejecting';
    wrap.appendChild(label);

    var input = document.createElement('input');
    input.type = 'text';
    input.id = reasonId;
    wrap.appendChild(input);

    if (reasonErrors[record.id]) {
      var errorId = 'reason-error-' + record.id;
      var error = document.createElement('p');
      error.id = errorId;
      error.textContent = reasonErrors[record.id];
      wrap.appendChild(error);
      input.setAttribute('aria-describedby', errorId);
      input.setAttribute('aria-invalid', 'true');
    }

    var confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.textContent = 'Confirm rejection';
    confirmBtn.addEventListener('click', function () {
      var reason = input.value.trim();
      focusRecordOnRender = record.id;
      if (!reason) {
        reasonErrors[record.id] = 'A reason is required.';
        render();
        return;
      }
      delete reasonErrors[record.id];
      delete rejecting[record.id];
      setDecision(record.id, {
        record_id: record.id,
        review_status: 'rejected',
        level: null,
        chosen_level: getLevel(),
        reason: reason
      });
    });
    wrap.appendChild(confirmBtn);

    var cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', function () {
      delete rejecting[record.id];
      delete reasonErrors[record.id];
      focusRecordOnRender = record.id;
      render();
    });
    wrap.appendChild(cancelBtn);

    return wrap;
  }

  /* Warnings, in the words the data gives them — never the internal "kind"
   * (e.g. "weak_match"). The label is what a reviewer should read; the kind
   * is just how the system files it. */
  function warningList(flags) {
    var wrap = document.createElement('div');

    if (!flags || !flags.length) {
      return wrap;
    }

    var h = document.createElement('p');
    h.textContent = 'Warnings';
    wrap.appendChild(h);

    var ul = document.createElement('ul');
    flags.forEach(function (flag) {
      var li = document.createElement('li');
      li.textContent = flag.detail ? flag.label + ' — ' + flag.detail : flag.label;
      ul.appendChild(li);
    });
    wrap.appendChild(ul);

    return wrap;
  }

  /* Hard to miss, impossible to dismiss: no set has been checked by a person
   * yet means nothing from this run can go to a district. */
  function lockBanner() {
    if (!currentSet || currentSet.publishable) {
      return null;
    }

    var banner = document.createElement('div');
    banner.setAttribute('role', 'alert');

    var h = document.createElement('p');
    h.textContent = 'Not checked by a person yet.';
    banner.appendChild(h);

    var p = document.createElement('p');
    p.textContent = 'Nobody has reviewed the boundary notes for this standards ' +
      'set. These results cannot go to a district until that happens.';
    banner.appendChild(p);

    return banner;
  }

  function evidenceItem(record) {
    var lesson = record.lesson;
    var decision = D.get(record.id);
    var li = document.createElement('li');

    var unitLabel = lesson.displayed_number
      ? 'Unit ' + lesson.displayed_number + ' — ' + lesson.unit_name
      : lesson.unit_name;

    var title = document.createElement('p');
    title.textContent = lesson.lesson_name + ' (' + unitLabel + ', lesson ' +
      lesson.lesson_token + ') — proposed at ' + record.level;
    li.appendChild(title);

    /* Stale is the most important thing on the screen: this was already
     * accepted, and the lesson has since changed underneath it. It must say
     * that plainly, regardless of whatever fresh decision gets made below. */
    if (record.review_status === 'stale') {
      var stale = document.createElement('p');
      stale.textContent = 'This was accepted before. The lesson has changed since — it needs review again.';
      li.appendChild(stale);
    }

    var objective = document.createElement('p');
    objective.textContent = lesson.has_objectives && lesson.objectives && lesson.objectives.length
      ? 'Objective: ' + lesson.objectives.join(' ')
      : 'No stated objective.';
    li.appendChild(objective);

    var evidence = document.createElement('p');
    evidence.textContent = record.evidence;
    li.appendChild(evidence);

    if (record.note) {
      var note = document.createElement('p');
      note.textContent = 'Note: ' + record.note;
      li.appendChild(note);
    }

    li.appendChild(warningList(record.flags));

    var levelLabel = document.createElement(record.is_choice_level ? 'p' : 'label');
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
      var choiceNote = document.createElement('p');
      choiceNote.textContent = 'Optional evidence: only ' + record.choice_option +
        ' does this. Cannot count as full coverage.';
      li.appendChild(choiceNote);
    }

    if (rejecting[record.id]) {
      li.appendChild(reasonFieldFor(record, currentLevel));
      return li;
    }

    var acceptBtn = document.createElement('button');
    acceptBtn.id = 'accept-' + record.id;
    acceptBtn.type = 'button';
    acceptBtn.textContent = 'Accept';
    acceptBtn.addEventListener('click', function () {
      var chosen = currentLevel();
      focusRecordOnRender = record.id;
      setDecision(record.id, {
        record_id: record.id,
        review_status: 'accepted',
        level: chosen === record.level ? null : chosen,
        chosen_level: chosen,
        reason: null
      });
    });
    li.appendChild(acceptBtn);

    var rejectBtn = document.createElement('button');
    rejectBtn.id = 'reject-' + record.id;
    rejectBtn.type = 'button';
    rejectBtn.textContent = 'Reject';
    rejectBtn.addEventListener('click', function () {
      rejecting[record.id] = true;
      focusRecordOnRender = record.id;
      render();
    });
    li.appendChild(rejectBtn);

    var status = document.createElement('p');
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
    var wrap = document.createElement('div');

    var h = document.createElement('p');
    h.textContent = 'Proposed evidence';
    wrap.appendChild(h);

    if (!records || !records.length) {
      var label = document.createElement('p');
      label.textContent = noEvidenceLabel(standard, outcome);
      wrap.appendChild(label);

      var why = document.createElement('p');
      why.textContent = (outcome && outcome.rationale) || 'No evidence proposed.';
      wrap.appendChild(why);

      return wrap;
    }

    var ul = document.createElement('ul');
    records.forEach(function (record) {
      ul.appendChild(evidenceItem(record));
    });
    wrap.appendChild(ul);

    return wrap;
  }

  function render() {
    var item = items[index];
    var standard = item.standard;

    mount.innerHTML = '';

    var banner = lockBanner();
    if (banner) {
      mount.appendChild(banner);
    }

    var progress = document.createElement('p');
    progress.textContent = 'Decisions: ' + D.count() + ' of ' + totalRecords + ' lessons reviewed.';
    mount.appendChild(progress);

    var position = document.createElement('p');
    position.textContent = 'Standard ' + (index + 1) + ' of ' + items.length;
    mount.appendChild(position);

    var heading = document.createElement('h3');
    heading.id = 'standard-heading';
    heading.tabIndex = -1;
    heading.textContent = standard.identifier;
    mount.appendChild(heading);

    var statement = document.createElement('p');
    statement.textContent = standard.statement;
    mount.appendChild(statement);

    mount.appendChild(boundaryList('Counts as teaching it', standard.boundary_includes));
    mount.appendChild(boundaryList('Does not count', standard.boundary_excludes));
    mount.appendChild(evidenceList(standard, item.outcome, item.records));

    var nav = document.createElement('p');

    var prev = document.createElement('button');
    prev.type = 'button';
    prev.textContent = 'Back';
    prev.disabled = index === 0;
    prev.addEventListener('click', function () {
      index -= 1;
      focusStandardOnRender = true;
      render();
    });
    nav.appendChild(prev);

    var next = document.createElement('button');
    next.type = 'button';
    next.textContent = 'Next';
    next.disabled = index === items.length - 1;
    next.addEventListener('click', function () {
      index += 1;
      focusStandardOnRender = true;
      render();
    });
    nav.appendChild(next);

    mount.appendChild(nav);

    var downloadBtn = document.createElement('button');
    downloadBtn.type = 'button';
    downloadBtn.textContent = 'Download decisions';
    downloadBtn.addEventListener('click', D.save);
    mount.appendChild(downloadBtn);

    var canPublish = !!(currentSet && currentSet.publishable);

    var publishBtn = document.createElement('button');
    publishBtn.type = 'button';
    publishBtn.textContent = 'Publish to district';
    publishBtn.disabled = !canPublish;
    mount.appendChild(publishBtn);

    if (!canPublish) {
      var why = document.createElement('p');
      why.textContent = 'Publishing is off until this standards set has been checked by a person.';
      mount.appendChild(why);
    }

    if (focusStandardOnRender) {
      focusStandardOnRender = false;
      heading.focus();
      announcer.textContent = 'Standard ' + (index + 1) + ' of ' + items.length +
        ': ' + standard.identifier + '. ' + standard.statement;
    } else if (focusRecordOnRender !== null) {
      var recordId = focusRecordOnRender;
      focusRecordOnRender = null;
      var target = rejecting[recordId]
        ? document.getElementById('reason-' + recordId)
        : (D.get(recordId)
          ? document.getElementById('status-' + recordId)
          : document.getElementById('accept-' + recordId));
      if (target) {
        target.focus();
      }
    }
  }

  function start() {
    if (S.isFilePath()) {
      say('This page needs to be served before it can read any data.');
      return;
    }

    say('Loading the review queue…');

    Promise.all([S.load('review-queue'), S.load('run'), S.load('standards-sets')])
      .then(function (results) {
        var queue = results[0];
        var run = results[1];
        var sets = results[2].items || [];

        items = queue.items || [];
        index = 0;
        totalRecords = items.reduce(function (sum, item) {
          return sum + (item.records ? item.records.length : 0);
        }, 0);

        currentSet = sets.filter(function (set) {
          return set.id === run.set_id;
        })[0] || null;

        if (!items.length) {
          say('The queue is empty.');
          return;
        }

        render();
      })
      .catch(function (error) {
        say('The review queue could not be read. ' + error.message);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
