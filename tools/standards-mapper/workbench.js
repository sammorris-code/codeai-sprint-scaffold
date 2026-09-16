/* workbench.js — loads the screen's data once, then hands it to each panel.
 *
 * Every panel on this page needs some of the same four things: the run, the
 * coverage numbers, the standards sets and the courses. Before this file
 * existed each panel fetched its own copy, so opening the page asked for the
 * run twice and the sets twice, and two panels could disagree about what they
 * were showing if one request failed and the other did not.
 *
 * One load, one shared context, one place that handles "this page was opened
 * from a file path" and "the data could not be read".
 *
 * Reads window.StandardsSource (loader.js). Calls, in order, whichever of
 * RunForm, RunSummary and ReviewQueue are present.
 */

(function () {
  'use strict';

  var S = window.StandardsSource;

  /* The panels, in the order a reader meets them down the page. Named rather
   * than discovered, so a typo in a panel's global is a visible failure here
   * instead of a panel that silently never renders. */
  function panels() {
    return [window.RunForm, window.RunSummary, window.ReviewQueue,
            window.QueueActions];
  }

  function each(method, argument) {
    panels().forEach(function (panel) {
      if (panel && typeof panel[method] === 'function') {
        panel[method](argument);
      }
    });
  }

  /* Ties the run to the set and course it was run against. The run carries
   * ids; a person needs names. Doing it once here means no panel has to know
   * how that lookup works. */
  function contextFrom(results) {
    var sets = results[0].items || [];
    var courses = results[1].items || [];
    var run = results[2];

    function byId(list, id) {
      return list.filter(function (entry) { return entry.id === id; })[0] || null;
    }

    return {
      sets: sets,
      courses: courses,
      run: run,
      coverage: results[3],
      queue: results[4],
      set: byId(sets, run.set_id),
      course: byId(courses, run.course_id)
    };
  }

  function start() {
    if (S.isFilePath()) {
      each('needsServing');
      return;
    }

    Promise.all([
      S.load('standards-sets'),
      S.load('courses'),
      S.load('run'),
      S.load('coverage'),
      S.load('review-queue')
    ])
      .then(function (results) {
        each('render', contextFrom(results));
      })
      .catch(function (error) {
        each('showError', error);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
