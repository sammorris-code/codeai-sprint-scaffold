/* mapper.js — choosing what to review.
 *
 * Two menus: a standards set and a course. Between them they name a piece of
 * work — "Oklahoma against AI Foundations" — and workbench.js turns that into
 * the newest run for the pair. Nobody types a run id.
 *
 * Before this existed, the set menu listed six US states written into the page
 * by hand. That is the thing this file removes. No state is built into any
 * tool: the menu shows whichever standards sets the store holds, and a set
 * that nobody has ingested does not appear.
 *
 * It fetches nothing. workbench.js owns loading and hands this panel the
 * catalogue, then the run it settled on.
 */

window.RunForm = (function () {
  'use strict';

  var S = window.StandardsSource;

  var setSelect = document.getElementById('framework');
  var courseSelect = document.getElementById('course');
  var status = document.getElementById('source-status');
  var fallback = document.getElementById('needs-serving');
  var form = document.getElementById('run-form');

  var wired = false;
  var filled = false;

  /* Replaces a menu's options, keeping a placeholder first so the page can
   * show "nothing chosen" without inventing a choice on the reviewer's
   * behalf. */
  function fillSelect(select, options, placeholder) {
    select.innerHTML = '';
    var first = document.createElement('option');
    first.value = '';
    first.textContent = placeholder;
    select.appendChild(first);

    options.forEach(function (option) {
      var el = document.createElement('option');
      el.value = option.value;
      el.textContent = option.label;
      select.appendChild(el);
    });
    select.disabled = false;
  }

  /* Changing either menu asks for that pair's newest run. There is no submit
   * button: the menus are the question, and waiting for a second click to
   * answer it is a step that earns nothing. */
  function wire() {
    if (wired) { return; }
    wired = true;

    function choose() {
      window.Workbench.choose(Number(setSelect.value) || null,
                              Number(courseSelect.value) || null);
    }

    setSelect.addEventListener('change', choose);
    courseSelect.addEventListener('change', choose);
  }

  function fillMenus(ctx) {
    fillSelect(setSelect, ctx.sets.map(function (set) {
      return { value: String(set.id), label: set.title || S.setLabel(set) };
    }), ctx.sets.length ? 'Choose a standards set' : 'No standards sets yet');

    fillSelect(courseSelect, ctx.courses.map(function (course) {
      return { value: String(course.id), label: course.course_name };
    }), ctx.courses.length ? 'Choose a course' : 'No courses yet');

    if (!ctx.sets.length) {
      setSelect.disabled = true;
      say('The store holds no standards sets. Ingest one to begin.');
      return;
    }

    wire();
    say('');
  }

  /* When a run arrives from a link rather than from these menus, the menus
   * have to catch up or they describe something that is not on screen. */
  function syncTo(ctx) {
    if (ctx.set) { setSelect.value = String(ctx.set.id); }
    if (ctx.course) { courseSelect.value = String(ctx.course.id); }
    say('');
  }

  function say(message) {
    status.textContent = message;
  }

  /* Called twice: once with the catalogue, then again with each run. The
   * menus are built once - rebuilding them on every run would throw away the
   * reviewer's selection and put it back a moment later. */
  function render(ctx) {
    if (ctx.sets && !filled) {
      filled = true;
      fillMenus(ctx);
    }
    if (ctx.run) {
      syncTo(ctx);
    }
  }

  /* The page was opened from a file path. Say what happened and what to do
   * about it, rather than leaving two empty menus and no explanation. */
  function needsServing() {
    fallback.hidden = false;
    form.hidden = true;
  }

  function showMessage(text) {
    /* Only the catalogue's own trouble belongs on this line. A message about
     * one run is the run panel's to show; repeating it here would say the
     * menus are broken when they are fine. */
    if (!wired) { say(text); }
  }

  return {
    render: render,
    needsServing: needsServing,
    showMessage: showMessage
  };
})();
