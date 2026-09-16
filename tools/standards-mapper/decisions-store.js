/* decisions-store.js — the one place a reviewer's decisions live and are saved.
 *
 * Today "saving" means holding decisions in memory and letting the reviewer
 * download them as a file. Later this is the one file that changes: save()
 * sends each decision to PATCH /api/records/{id} instead of building a file.
 * Nothing in queue.js should need to change when that happens.
 *
 * Mirrors the split loader.js makes for reads — one small file owns "how",
 * everything else just calls it.
 */

window.ReviewDecisions = (function () {
  'use strict';

  // record id -> decision
  var decisions = {};

  function get(recordId) {
    return decisions[recordId] || null;
  }

  function set(recordId, decision) {
    decisions[recordId] = decision;
  }

  function count() {
    return Object.keys(decisions).length;
  }

  function all() {
    return Object.keys(decisions).map(function (id) {
      return decisions[id];
    });
  }

  // ---- Saving. This is where "only that part changes" happens. ----------

  /* Hands the browser a file. One place, so JSON and CSV cannot drift in how
   * they clean up after themselves. */
  function download(text, filename, mime) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function save() {
    download(JSON.stringify(all(), null, 2), 'review-decisions.json',
             'application/json');
  }

  /* One CSV field.
   *
   * Always quoted, and every quote inside doubled. Reviewers type rejection
   * reasons by hand, and a reason containing a comma would otherwise split
   * into two columns and silently corrupt the row. Quoting everything costs
   * nothing and removes the question. */
  function csvField(value) {
    if (value === null || value === undefined) {
      return '""';
    }
    return '"' + String(value).replace(/"/g, '""') + '"';
  }

  /* The spreadsheet a reviewer can send to somebody who does not have this
   * tool open. It is a report, not the record: save() produces what the
   * service will take. */
  function saveCsv() {
    var header = ['record_id', 'standard', 'lesson', 'decision', 'depth', 'reason'];
    var lines = [header.map(csvField).join(',')];

    all().forEach(function (decision) {
      lines.push([
        decision.record_id,
        decision.standard_identifier,
        decision.lesson_name,
        decision.review_status,
        decision.chosen_level,
        decision.reason
      ].map(csvField).join(','));
    });

    /* CRLF and a UTF-8 byte order mark, both for Excel: without the mark it
     * reads the file as the local code page and mangles any accented name. */
    download('\ufeff' + lines.join('\r\n') + '\r\n',
             'review-decisions.csv', 'text/csv;charset=utf-8');
  }

  return {
    get: get,
    set: set,
    count: count,
    all: all,
    save: save,
    saveCsv: saveCsv
  };
})();
