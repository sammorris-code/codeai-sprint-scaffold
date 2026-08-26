/* ==========================================================================
   tutorials.js

   Two jobs:
     1. A tab strip (real tabs: arrow keys, aria-selected, deep links).
     2. A small markdown renderer, so docs/*.md stays the single source of
        truth and this page never has its own copy of the tutorials.

   The renderer handles the subset of markdown our docs actually use:
   headings, fenced code, inline code, bold, italic, links, bare URLs, bullet
   and numbered lists, tables, and horizontal rules. It is not a general
   markdown library and does not need to be. If a doc starts using something
   it does not understand, add it here.

   Note: fetch() cannot read files from a file:// path, so this page needs to
   be served. python3 -m http.server 8000 is enough. The page says so itself
   rather than sitting there empty.
   ========================================================================== */

(function () {
  'use strict';

  /* --- Markdown ---------------------------------------------------------- */

  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function slugify(text) {
    return text
      .toLowerCase()
      .replace(/`/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  // Inline formatting. Order matters: escape first so that markup we generate
  // below survives, then pull code spans out so their contents are not
  // formatted again as bold or links.
  function inline(text) {
    var codeSpans = [];
    var out = escapeHtml(text);

    out = out.replace(/`([^`]+)`/g, function (match, code) {
      codeSpans.push(code);
      return '@@' + (codeSpans.length - 1) + '@@';
    });

    out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (match, label, href) {
      return '<a href="' + href + '">' + label + '</a>';
    });

    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/(^|[^*\w])\*([^*\n]+)\*/g, '$1<em>$2</em>');

    // Bare URLs, but not ones already sitting inside an href we just built.
    out = out.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, function (m, before, url) {
      return before + '<a href="' + url + '">' + url + '</a>';
    });

    return out.replace(/@@(\d+)@@/g, function (match, index) {
      return '<code>' + codeSpans[Number(index)] + '</code>';
    });
  }

  function splitTableRow(line) {
    return line
      .replace(/^\s*\|/, '')
      .replace(/\|\s*$/, '')
      .split('|')
      .map(function (cell) { return cell.trim(); });
  }

  var BLOCK_START = /^(#{1,6}\s|```|---+\s*$|\s*([-*]|\d+\.)\s|\s*\|)/;

  function render(markdown, idPrefix) {
    var lines = markdown.replace(/\r\n?/g, '\n').split('\n');
    var html = [];
    var headings = [];
    var usedIds = {};
    var i = 0;

    function uniqueId(text) {
      var base = idPrefix + '-' + slugify(text);
      var id = base;
      var n = 2;
      while (usedIds[id]) { id = base + '-' + n; n++; }
      usedIds[id] = true;
      return id;
    }

    while (i < lines.length) {
      var line = lines[i];

      // Fenced code block.
      var fence = line.match(/^```\s*([\w+-]*)\s*$/);
      if (fence) {
        var lang = fence[1];
        var code = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) {
          code.push(lines[i]);
          i++;
        }
        i++;
        html.push(
          '<pre class="code"' + (lang ? ' data-lang="' + lang + '"' : '') +
          '><code>' + escapeHtml(code.join('\n')) + '</code></pre>'
        );
        continue;
      }

      // Horizontal rule.
      if (/^---+\s*$/.test(line)) {
        html.push('<hr>');
        i++;
        continue;
      }

      // Heading. Level 2 headings become the table of contents.
      var heading = line.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        var level = heading[1].length;
        var raw = heading[2].trim();
        var id = uniqueId(raw);
        if (level === 2) {
          headings.push({ id: id, text: raw.replace(/`/g, '') });
        }
        html.push('<h' + level + ' id="' + id + '">' + inline(raw) + '</h' + level + '>');
        i++;
        continue;
      }

      // Table: a pipe row followed by a divider row.
      if (/^\s*\|/.test(line) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
        var head = splitTableRow(line);
        i += 2;
        var body = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) {
          body.push(splitTableRow(lines[i]));
          i++;
        }
        var table = ['<div class="table-scroll"><table class="data-table"><thead><tr>'];
        head.forEach(function (cell) {
          table.push('<th scope="col">' + inline(cell) + '</th>');
        });
        table.push('</tr></thead><tbody>');
        body.forEach(function (row) {
          table.push('<tr>');
          row.forEach(function (cell) {
            table.push('<td>' + inline(cell) + '</td>');
          });
          table.push('</tr>');
        });
        table.push('</tbody></table></div>');
        html.push(table.join(''));
        continue;
      }

      // List. Continuation lines are indented, so fold them into the item.
      if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
        var ordered = /^\s*\d+\./.test(line);
        var items = [];
        while (i < lines.length) {
          var item = lines[i].match(/^\s*([-*]|\d+\.)\s+(.*)$/);
          if (item) {
            items.push(item[2]);
            i++;
            while (i < lines.length &&
                   /^\s+\S/.test(lines[i]) &&
                   !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
              items[items.length - 1] += ' ' + lines[i].trim();
              i++;
            }
          } else if (!lines[i].trim() && /^\s*([-*]|\d+\.)\s+/.test(lines[i + 1] || '')) {
            i++;
          } else {
            break;
          }
        }
        var tag = ordered ? 'ol' : 'ul';
        html.push('<' + tag + ' class="doc-list">' +
          items.map(function (text) { return '<li>' + inline(text) + '</li>'; }).join('') +
          '</' + tag + '>');
        continue;
      }

      if (!line.trim()) {
        i++;
        continue;
      }

      // Paragraph: run until a blank line or the start of another block.
      var paragraph = [];
      while (i < lines.length && lines[i].trim() && !BLOCK_START.test(lines[i])) {
        paragraph.push(lines[i].trim());
        i++;
      }
      html.push('<p>' + inline(paragraph.join(' ')) + '</p>');
    }

    return { html: html.join('\n'), headings: headings };
  }

  /* --- Loading ----------------------------------------------------------- */

  function buildToc(nav, headings) {
    if (!headings.length) { return; }
    var list = headings.map(function (h) {
      return '<li><a href="#' + h.id + '">' + escapeHtml(h.text) + '</a></li>';
    }).join('');
    nav.innerHTML = '<h2 class="toc-title">On this page</h2><ul>' + list + '</ul>';
  }

  function showError(panel, tab, message) {
    var status = panel.querySelector('.doc-status');
    status.classList.add('doc-status--error');
    status.innerHTML = message +
      ' <a href="' + tab.dataset.src + '">Open the markdown file directly.</a>';
  }

  function load(tab, panel) {
    if (panel.dataset.loaded) { return; }
    panel.dataset.loaded = 'true';

    var status = panel.querySelector('.doc-status');
    var layout = panel.querySelector('.doc-layout');

    if (location.protocol === 'file:') {
      showError(panel, tab,
        'This page reads the markdown files at runtime, which browsers block ' +
        'on a file:// path. Serve the folder — <code>python3 -m http.server 8000</code> — ' +
        'and reload.');
      return;
    }

    fetch(tab.dataset.src)
      .then(function (response) {
        if (!response.ok) {
          throw new Error(response.status + ' ' + response.statusText);
        }
        return response.text();
      })
      .then(function (markdown) {
        var result = render(markdown, tab.dataset.track);
        panel.querySelector('.doc').innerHTML = result.html;
        buildToc(panel.querySelector('.doc-toc'), result.headings);
        status.hidden = true;
        layout.hidden = false;
      })
      .catch(function (error) {
        showError(panel, tab, 'Could not load ' + tab.dataset.src + ' (' + error.message + ').');
      });
  }

  /* --- Tabs -------------------------------------------------------------- */

  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
  if (!tabs.length) { return; }

  function panelFor(tab) {
    return document.getElementById(tab.getAttribute('aria-controls'));
  }

  function select(tab, focusTab) {
    tabs.forEach(function (other) {
      var isCurrent = other === tab;
      other.setAttribute('aria-selected', isCurrent ? 'true' : 'false');
      other.tabIndex = isCurrent ? 0 : -1;
      panelFor(other).hidden = !isCurrent;
    });
    if (focusTab) { tab.focus(); }
    load(tab, panelFor(tab));
    if (history.replaceState) {
      history.replaceState(null, '', '#' + tab.dataset.track);
    }
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () { select(tab, false); });
    tab.addEventListener('keydown', function (event) {
      var index = tabs.indexOf(tab);
      var next = null;
      if (event.key === 'ArrowRight') { next = tabs[(index + 1) % tabs.length]; }
      if (event.key === 'ArrowLeft') { next = tabs[(index - 1 + tabs.length) % tabs.length]; }
      if (event.key === 'Home') { next = tabs[0]; }
      if (event.key === 'End') { next = tabs[tabs.length - 1]; }
      if (next) {
        event.preventDefault();
        select(next, true);
      }
    });
  });

  // Deep link: #git or #claude-code opens that track.
  var requested = tabs.filter(function (tab) {
    return '#' + tab.dataset.track === location.hash;
  })[0];

  select(requested || tabs[0], false);
}());
