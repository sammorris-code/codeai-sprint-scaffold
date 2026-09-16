/* loader.js — the one place that knows where the data comes from.
 *
 * Today it reads the fixtures in contract/fixtures/. Later it reads the API.
 * Change SOURCE below and nothing else in the page has to change.
 *
 * Two deliberate choices, both worth keeping:
 *
 * 1. This is a plain script, not an ES module. A module is blocked outright
 *    when the page is opened from a file path, so none of our code would run
 *    and the page would sit there empty. A plain script always runs. The fetch
 *    inside it fails instead, and we catch that and show a panel that says what
 *    to do. A page that explains itself beats a page that is blank.
 *
 * 2. Every path here is relative. Never write "/contract/...". Every pull
 *    request is published under pr-preview/pr-<number>/, and a leading slash
 *    escapes that folder and quietly loads the live site's file instead. The
 *    preview would then show the wrong thing rather than fail.
 */

window.StandardsSource = (function () {
  'use strict';

  var SOURCE = {
    // ---- Reading fixtures. This is where we are now. --------------------
    mode: 'fixtures',
    base: '../../contract/fixtures',

    // ---- Reading the API. Swap mode to 'api' and set the base. ----------
    // mode: 'api',
    //
    // Against a service on your own machine:
    // base: 'http://localhost:8000/api',
    //
    // Against the hosted one, where this page is served BY that service and
    // so shares its origin:
    // base: '../../api',
    //
    // Relative, not '/api'. A leading slash escapes pr-preview/pr-<number>/
    // and loads the live site's data instead - the preview then shows the
    // wrong thing rather than failing.
    //
    // Same origin is not a nicety there. The hosted service sits behind basic
    // auth, and cross-origin the browser's preflight OPTIONS carries no
    // credentials, gets a 401, and every write fails as a CORS error naming
    // nothing. Same origin there is no preflight, and the credentials the
    // browser already holds are sent - which is what `credentials:
    // 'same-origin'` below is for.

    paths: {
      fixtures: {
        'standards-sets': '/standards-sets.json',
        'courses': '/courses.json',
        'review-queue': '/review-queue.json',
        'run': '/run.json',
        'coverage': '/coverage.json',
        'run-diff': '/run-diff.json'
      },
      api: {
        'standards-sets': '/standards-sets',
        'courses': '/courses',
        'review-queue': '/runs/1/queue',
        'run': '/runs/1',
        'coverage': '/runs/1/coverage',
        'run-diff': '/runs/1/diff'
      }
    }
  };

  /* True when the page was opened by double-clicking the file rather than
   * through a web address. fetch() cannot work here, and that is a browser
   * rule, not a bug in this page. */
  function isFilePath() {
    return window.location.protocol === 'file:';
  }

  function urlFor(resource) {
    var path = SOURCE.paths[SOURCE.mode][resource];
    if (!path) {
      throw new Error('loader.js knows no resource named "' + resource + '"');
    }
    return SOURCE.base + path;
  }

  /* Reads one resource. Resolves with the parsed body.
   * Rejects with an Error carrying a .kind the page can branch on:
   *   'file-path'  the page needs serving
   *   'not-found'  the data is not where we looked
   *   'network'    everything else */
  function load(resource) {
    if (isFilePath()) {
      var blocked = new Error('This page was opened from a file path.');
      blocked.kind = 'file-path';
      return Promise.reject(blocked);
    }

    return fetch(urlFor(resource), { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) {
          var bad = new Error('The server answered ' + response.status +
                              ' for ' + urlFor(resource));
          bad.kind = response.status === 404 ? 'not-found' : 'network';
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
   * now. See contract/REVIEW-DESIGN.md, and runStatus() below for the rule that
   * actually gates a release. */
  function setStatus(set) {
    if (set.all_boundaries_checked) {
      return { text: 'Notes checked by a person', all_boundaries_checked: true };
    }
    return { text: 'Notes are drafts', all_boundaries_checked: false };
  }

  /* The real release gate, in one place: a run is published when a person has
   * approved it. Nothing about the set's boundary notes appears here, because
   * nothing about them holds a release any more.
   *
   * The service agrees - service/app/main.py, approve() - and this is the only
   * place the interface states the rule. */
  function runStatus(run) {
    if (!run) {
      return { published: false, text: 'No run loaded.' };
    }
    if (run.status === 'approved') {
      return {
        published: true,
        text: 'Approved' + (run.approved_by ? ' by ' + run.approved_by : '') +
              '. These results are on the public site.'
      };
    }
    return {
      published: false,
      text: 'Not approved yet, so nothing here is on the public site. ' +
            'A person approves the run when they are done reviewing it.'
    };
  }

  return {
    load: load,
    isFilePath: isFilePath,
    urlFor: urlFor,
    setLabel: setLabel,
    setStatus: setStatus,
    runStatus: runStatus,
    mode: SOURCE.mode
  };
})();
