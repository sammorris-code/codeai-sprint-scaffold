/* workbench.js — decides which run is on screen, and hands it to the panels.
 *
 * A reviewer knows "Oklahoma" and "AI Foundations". They do not know that the
 * run they want is number 7, and they should never have to. So this file asks
 * the service for the runs matching a standards set and a course, takes the
 * newest, and loads that. The run id stays an implementation detail - visible
 * in the address bar so a run can be linked to, never something to type.
 *
 * There is no global "newest run": a set against one course and the same set
 * against another are separate work and neither supersedes the other. The only
 * place a bare newest is used is the very first load, before anybody has
 * chosen anything, and the header says exactly which run that landed on.
 *
 * Panels implement whichever of these they need:
 *   render(context)      the run and everything about it
 *   showMessage(text)    a plain line, when there is nothing to render
 *   needsServing()       the page was opened from a file path (RunForm only)
 */

window.Workbench = (function () {
  'use strict';

  var S = window.StandardsSource;

  var sets = [];
  var courses = [];

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

  function byId(list, id) {
    return list.filter(function (entry) { return entry.id === id; })[0] || null;
  }

  /* A run id in the address bar. Deep links to a specific historical run keep
   * working; it is not how anybody arrives at their own work. */
  function runIdFromUrl() {
    var match = /[?&]run=(\d+)/.exec(window.location.search);
    return match ? Number(match[1]) : null;
  }

  /* Keeps the address bar pointing at what is on screen, so the page can be
   * linked or reloaded. replaceState, not pushState: changing the menus is
   * not navigation and should not fill up the back button. */
  function rememberRun(runId) {
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, '', '?run=' + runId);
    }
  }

  // ---- What went wrong, in words -----------------------------------------

  function describe(error) {
    if (error.kind === 'file-path') {
      return 'This page needs to be served before it can read any data.';
    }
    if (error.kind === 'no-service') {
      return 'No standards service is answering at this address. This page ' +
             'reads the live service, so it only works where the service is ' +
             'serving it — not on the published site or a pull-request ' +
             'preview. To work against sample data instead, swap the two ' +
             'lines at the top of loader.js.';
    }
    if (error.kind === 'not-found') {
      return 'That run is not in the store. It may have been removed, or the ' +
             'id in the address may be wrong. Choose a standards set and a ' +
             'course above to pick one up again.';
    }
    return 'The data could not be read. ' + error.message;
  }

  function failed(error) {
    each('showMessage', describe(error));
  }

  // ---- Loading -----------------------------------------------------------

  /* Everything about one run, loaded together so no panel can render against
   * a half-built picture. `runs` is every run for the same set and course,
   * newest first, which is what lets the header say "run 2 of 3". */
  function showRun(runId) {
    each('showMessage', 'Loading run ' + runId + '…');

    return S.load('run', { runId: runId })
      .then(function (run) {
        return Promise.all([
          run,
          S.load('coverage', { runId: runId }),
          S.load('review-queue', { runId: runId }),
          S.load('runs', { setId: run.set_id, courseId: run.course_id })
        ]);
      })
      .then(function (results) {
        var run = results[0];
        var siblings = results[3].items || [];

        rememberRun(run.id);

        /* Before anything renders. Decisions are kept per run, and a panel
         * that read the count first would read the previous run's. */
        window.ReviewDecisions.setRun(run.id);

        each('render', {
          sets: sets,
          courses: courses,
          run: run,
          coverage: results[1],
          queue: results[2],
          runs: siblings,
          position: positionOf(run, siblings),
          set: byId(sets, run.set_id),
          course: byId(courses, run.course_id)
        });
      })
      .catch(failed);
  }

  /* "run 2 of 3", counting newest first the way the list arrives. */
  function positionOf(run, siblings) {
    for (var i = 0; i < siblings.length; i += 1) {
      if (siblings[i].id === run.id) {
        return { index: siblings.length - i, total: siblings.length };
      }
    }
    return { index: 1, total: Math.max(1, siblings.length) };
  }

  /* The newest run for one set against one course. Called when the menus
   * change - this is the ordinary way a reviewer gets to their work. */
  function choose(setId, courseId) {
    if (!setId || !courseId) {
      each('showMessage',
           'Choose a standards set and a course to see the latest run.');
      return Promise.resolve();
    }

    each('showMessage', 'Finding the latest run…');

    return S.load('runs', { setId: setId, courseId: courseId })
      .then(function (body) {
        var runs = body.items || [];
        if (!runs.length) {
          var set = byId(sets, setId);
          var course = byId(courses, courseId);
          each('showMessage',
               'No run yet for ' + (set ? set.title : 'that set') + ' against ' +
               (course ? course.course_name : 'that course') + '. Somebody has ' +
               'to start one before there is anything to review.');
          return null;
        }
        return showRun(runs[0].id);
      })
      .catch(failed);
  }

  function start() {
    if (S.isFilePath()) {
      each('needsServing');
      each('showMessage', describe({ kind: 'file-path' }));
      return;
    }

    each('showMessage', 'Reading the standards sets and courses…');

    Promise.all([S.load('standards-sets'), S.load('courses')])
      .then(function (results) {
        sets = results[0].items || [];
        courses = results[1].items || [];

        if (window.RunForm) {
          window.RunForm.render({ sets: sets, courses: courses });
        }

        var linked = runIdFromUrl();
        if (linked) {
          return showRun(linked);
        }

        /* Nothing chosen and nothing linked. Land on the most recently
         * created run so the page opens on work rather than on a prompt, and
         * let the header say which one it picked. */
        return S.load('runs').then(function (body) {
          var runs = body.items || [];
          if (!runs.length) {
            each('showMessage',
                 'The store holds no runs yet. Choose a standards set and a ' +
                 'course, then start one.');
            return null;
          }
          return showRun(runs[0].id);
        });
      })
      .catch(failed);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  return { choose: choose, showRun: showRun };
})();
