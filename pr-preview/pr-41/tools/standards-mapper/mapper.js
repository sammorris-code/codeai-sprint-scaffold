/* mapper.js — fills the two menus at the top of the page.
 *
 * Before this existed, the Framework menu listed six US states written into the
 * page by hand. That is the thing this file removes. No state is built into any
 * tool: the menu shows whichever standards sets the store holds, and a set that
 * nobody has ingested does not appear.
 *
 * It no longer fetches anything. workbench.js loads the page's data once and
 * hands it to every panel, this one included.
 */

window.RunForm = (function () {
  'use strict';

  var S = window.StandardsSource;

  var frameworkSelect = document.getElementById('framework');
  var courseSelect = document.getElementById('course');
  var status = document.getElementById('source-status');
  var fallback = document.getElementById('needs-serving');
  var form = document.getElementById('run-form');

  /* Replaces a menu's options. Keeps the first "Select a ..." option, because a
   * menu that starts on a real value invites an accidental run. */
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

  /* "1 course", "3 courses". Worth the six lines: this string is read by a
   * person every time the page loads. */
  function count(n, noun) {
    return n + ' ' + noun + (n === 1 ? '' : (noun.slice(-1) === 's' ? 'es' : 's'));
  }

  function say(message) {
    status.textContent = message;
  }

  function fill(ctx) {
    var sets = ctx.sets;
    var courses = ctx.courses;

    fillSelect(frameworkSelect, sets.map(function (set) {
      return {
        value: String(set.id),
        label: S.setLabel(set) + ' — ' + S.setStatus(set).text
      };
    }), sets.length ? 'Select a standards set' : 'No standards sets yet');

    fillSelect(courseSelect, courses.map(function (course) {
      return { value: String(course.id), label: course.course_name };
    }), courses.length ? 'Select a course' : 'No courses yet');

    if (!sets.length) {
      frameworkSelect.disabled = true;
      say('The store holds no standards sets. Ingest one to begin.');
      return;
    }

    /* This used to count the sets whose boundary notes nobody had checked and
     * report it here, back when that number decided whether results could
     * reach a district. It decides nothing now (contract/REVIEW-DESIGN.md), so
     * putting it in front of somebody about to start a run only invites them
     * to think they have a problem to clear first. Each set's own notes state
     * is still on its line in the menu, which is where it is useful. */
    say(count(sets.length, 'standards set') + ' and ' +
        count(courses.length, 'course') + ' in the store.');
  }

  /* The page was opened from a file path. Say what happened and what to do
   * about it, rather than leaving two empty menus and no explanation. */
  function needsServing() {
    fallback.hidden = false;
    form.hidden = true;
    say('This page needs to be served before it can read any data.');
  }

  function showError(error) {
    say('The data could not be read. ' + error.message);
    frameworkSelect.disabled = true;
    courseSelect.disabled = true;
  }

  return {
    render: fill,
    needsServing: needsServing,
    showError: showError
  };
})();
