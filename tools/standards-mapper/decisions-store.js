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
  function save() {
    var payload = all();
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'review-decisions.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return {
    get: get,
    set: set,
    count: count,
    all: all,
    save: save
  };
})();
