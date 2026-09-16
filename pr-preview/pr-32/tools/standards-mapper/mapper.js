/* mapper.js — fills the two menus on this page from the data source.
 *
 * Before this existed, the Framework menu listed six US states written into the
 * page by hand. That is the thing this file removes. No state is built into any
 * tool: the menu shows whichever standards sets the store holds, and a set that
 * nobody has ingested does not appear.
 *
 * Reads window.StandardsSource, defined in loader.js.
 */

(function () {
  'use strict';

  var S = window.StandardsSource;

  var frameworkSelect = document.getElementById('framework');
  var courseSelect = document.getElementById('course');
  var status = document.getElementById('source-status');
  var fallback = document.getElementById('needs-serving');
  var form = document.getElementById('run-form');

  /* Replaces a menu's options. Keeps the first "Select a ..." option, because a
   * menu that starts on a real value invites an accidental run. */
  function fill(select, options, placeholder) {
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

  /* The page was opened from a file path. Say what happened and what to do
   * about it, rather than leaving two empty menus and no explanation. */
  function showFallback() {
    fallback.hidden = false;
    form.hidden = true;
    say('This page needs to be served before it can read any data.');
  }

  function showError(error) {
    say('The data could not be read. ' + error.message);
    frameworkSelect.disabled = true;
    courseSelect.disabled = true;
  }

  function start() {
    if (S.isFilePath()) {
      showFallback();
      return;
    }

    say('Reading the standards sets…');
    frameworkSelect.disabled = true;
    courseSelect.disabled = true;

    Promise.all([S.load('standards-sets'), S.load('courses')])
      .then(function (results) {
        var sets = results[0].items || [];
        var courses = results[1].items || [];

        fill(frameworkSelect, sets.map(function (set) {
          return {
            value: String(set.id),
            label: S.setLabel(set) + ' — ' + S.setStatus(set).text
          };
        }), sets.length ? 'Select a standards set' : 'No standards sets yet');

        fill(courseSelect, courses.map(function (course) {
          return { value: String(course.id), label: course.course_name };
        }), courses.length ? 'Select a course' : 'No courses yet');

        if (!sets.length) {
          frameworkSelect.disabled = true;
          say('The store holds no standards sets. Ingest one to begin.');
          return;
        }

        var unchecked = sets.filter(function (set) { return !set.all_boundaries_checked; }).length;
        say(count(sets.length, 'standards set') + ', ' +
            count(courses.length, 'course') + '. ' +
            (unchecked
              ? count(unchecked, 'set') + ' ' + (unchecked === 1 ? 'has' : 'have') +
                ' boundary notes that nobody has checked yet. Those notes are ' +
                'drafts; a reviewer checks one when an alignment turns on it.'
              : 'Every set has been checked by a person.'));
      })
      .catch(showError);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
