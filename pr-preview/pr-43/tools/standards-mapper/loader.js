/* loader.js — the one place that knows where the data comes from.
 *
 * Three deliberate choices, all worth keeping:
 *
 * 1. This is a plain script, not an ES module. A module is blocked outright
 *    when the page is opened from a file path, so none of our code would run
 *    and the page would sit there empty. A plain script always runs. The fetch
 *    inside it fails instead, and we catch that and show a panel that says what
 *    to do. A page that explains itself beats a page that is blank.
 *
 * 2. Every path here is relative. Never write "/api/...". Every pull request
 *    is published under pr-preview/pr-<number>/, and a leading slash escapes
 *    that folder and quietly loads the live site's data instead. The preview
 *    would then show the wrong thing rather than fail.
 *
 * 3. No run id is baked in. An earlier version hardcoded /runs/1, which was
 *    fine while the only data was a fixture holding one run. Against the real
 *    store it would have shown whichever run happened to be first, forever.
 *    Every run-scoped path is a function of the run being viewed.
 */

window.StandardsSource = (function () {
  'use strict';

  var SOURCE = {
    // ---- Reading the live service. This is where we are now. ------------
    //
    // Relative, because the service serves this page: the API is at
    // <wherever you loaded this from>/api. There is no hostname to configure
    // and none to get wrong.
    //
    // It must stay relative for two reasons. A leading slash escapes
    // pr-preview/pr-<number>/. And same origin means no CORS preflight -
    // the hosted service sits behind basic auth, and cross-origin the
    // browser's preflight OPTIONS carries no credentials, gets a 401, and
    // every write fails as a CORS error naming nothing. Same origin, the
    // credentials the browser already holds are sent, which is what
    // `credentials: 'same-origin'` below is for.
    //
    // NOTE: only the service-served copy can load data. On GitHub Pages and
    // in a pull-request preview there is no API behind ../../api, and the
    // page says so rather than showing an empty screen.
    mode: 'api',
    base: '../../api',

    // ---- Reading the fixtures instead. ----------------------------------
    // Swap the two lines above for these to work against sample data with no
    // service running - useful offline, and it is what the contract tests
    // compare the service against.
    //
    // mode: 'fixtures',
    // base: '../../contract/fixtures',
    //
    // Fixture mode ignores the run id: there is one run in the sample data
    // and every run-scoped file is a fixed file.

    paths: {
      fixtures: {
        'standards-sets': function () { return '/standards-sets.json'; },
        'courses': function () { return '/courses.json'; },
        'runs': function () { return '/runs.json'; },
        'run': function () { return '/run.json'; },
        'review-queue': function () { return '/review-queue.json'; },
        'coverage': function () { return '/coverage.json'; },
        'run-diff': function () { return '/run-diff.json'; }
      },
      api: {
        'standards-sets': function () { return '/standards-sets'; },
        'courses': function () { return '/courses'; },
        'runs': function (p) {
          return '/runs' + query({ set_id: p.setId, course_id: p.courseId });
        },
        'run': function (p) { return '/runs/' + needRun(p); },
        'review-queue': function (p) { return '/runs/' + needRun(p) + '/queue'; },
        'coverage': function (p) { return '/runs/' + needRun(p) + '/coverage'; },
        'run-diff': function (p) {
          return '/runs/' + needRun(p) + '/diff' +
                 query({ against: p.againstRunId });
        }
      }
    }
  };

  /* "?a=1&b=2", or "" when nothing was given. Undefined and null are left
   * out rather than sent as the strings "undefined" and "null", which the
   * service would reject as a bad integer. */
  function query(params) {
    var parts = [];
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value !== undefined && value !== null && value !== '') {
        parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(value));
      }
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  /* A run-scoped path with no run is a bug in the caller, and one that would
   * otherwise fetch "/runs/undefined" and report a confusing 422. */
  function needRun(p) {
    if (!p || p.runId === undefined || p.runId === null) {
      throw new Error('This resource needs a run id and none was given.');
    }
    return p.runId;
  }

  /* True when the page was opened by double-clicking the file rather than
   * through a web address. fetch() cannot work here, and that is a browser
   * rule, not a bug in this page. */
  function isFilePath() {
    return window.location.protocol === 'file:';
  }

  function urlFor(resource, params) {
    var build = SOURCE.paths[SOURCE.mode][resource];
    if (!build) {
      throw new Error('loader.js knows no resource named "' + resource + '"');
    }
    return SOURCE.base + build(params || {});
  }

  /* Reads one resource. Resolves with the parsed body.
   * Rejects with an Error carrying a .kind the page can branch on:
   *   'file-path'    the page needs serving
   *   'no-service'   nothing is answering at ../../api
   *   'not-found'    the service answered, but that run does not exist
   *   'network'      everything else */
  function load(resource, params) {
    if (isFilePath()) {
      var blocked = new Error('This page was opened from a file path.');
      blocked.kind = 'file-path';
      return Promise.reject(blocked);
    }

    var url;
    try {
      url = urlFor(resource, params);
    } catch (error) {
      error.kind = 'network';
      return Promise.reject(error);
    }

    return fetch(url, { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) {
          var bad = new Error('The server answered ' + response.status +
                              ' for ' + url);
          /* A 404 on a LIST endpoint means no service is answering here -
           * GitHub Pages returning its own not-found for a path with no API
           * behind it. A 404 on a run means the service answered and that
           * run is genuinely not there. They need different words on screen,
           * so they are told apart here rather than guessed at later. */
          if (response.status === 404) {
            bad.kind = (resource === 'standards-sets' || resource === 'courses' ||
                        resource === 'runs') ? 'no-service' : 'not-found';
          } else if (response.status === 401 || response.status === 403) {
            bad.kind = 'no-service';
          } else {
            bad.kind = 'network';
          }
          throw bad;
        }
        return response.json();
      })
      .catch(function (error) {
        if (!error.kind) { error.kind = 'network'; }
        throw error;
      });
  }

  /* One standards set, written the way a person reads it.
   * "DEMO · CS-DEMO · 2026". The interface never builds this string itself,
   * so every screen names a set the same way. */
  function setLabel(set) {
    return set.framework + ' · ' + set.standard_set + ' · ' + set.framework_year;
  }

  /* Plain words for the state of a set's boundary notes. The rule lives here
   * once. No screen re-derives it from boundary_provenance.
   *
   * This describes the notes and nothing else. It used to be read as though it
   * decided whether results could reach a district; it never decides anything
   * now. The rule that actually gates a release is an approved run, and it is
   * enforced by the service - contract/REVIEW-DESIGN.md. Nothing in the
   * interface needs to restate it. */
  function setStatus(set) {
    if (set.all_boundaries_checked) {
      return { text: 'Notes checked by a person', all_boundaries_checked: true };
    }
    return { text: 'Notes are drafts', all_boundaries_checked: false };
  }

  /* Plain words for a run's status, for a menu line. */
  function runStatusWord(run) {
    if (run.status === 'approved') { return 'approved'; }
    if (run.status === 'superseded') { return 'superseded'; }
    if (run.status === 'in_review') { return 'in review'; }
    return run.status;
  }

  return {
    load: load,
    isFilePath: isFilePath,
    urlFor: urlFor,
    setLabel: setLabel,
    setStatus: setStatus,
    runStatusWord: runStatusWord,
    mode: SOURCE.mode
  };
})();
