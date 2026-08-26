# CLAUDE.md

Project instructions for Claude Code. Read this before editing anything here.

## What this repository is

A deliberately primitive multi-page static website. It has two jobs: it is a
practice ground for a team learning git and Claude Code, and it is the starting
scaffold for a three-day product sprint. It is **not** a production site.

The seven pages under `tools/` each correspond to one candidate product from the
sprint's scoping work. `index.html` is the portal directory that links them.

## Hard constraints

These are the point of the repository, not oversights. Do not "fix" them.

- **No JavaScript.** No `<script>` tags, no inline event handlers, no framework,
  no build step, no `package.json`. Forms submit to `#` anchors and buttons do
  nothing. If a task seems to require JavaScript, say so and stop rather than
  adding it.
- **No visual styling.** `css/layout.css` contains layout properties only:
  display, grid, flex, gap, margin, padding, width, position, overflow,
  box-sizing. It must not gain `color`, `background`, `font-family`, `font-size`,
  `font-weight`, `border`, `border-radius`, `box-shadow`, or `transition`.
- **No inline `style` attributes** in any HTML file.
- **Per-tool styling goes in the tool's own folder.** When a team styles a page,
  create `tools/<name>/style.css` and uncomment the existing commented-out
  `<link>` in that page's `<head>`. Never put visual styling in the shared
  stylesheet.
- **This repository is public.** No student data, no real district contacts, no
  credentials, no internal pricing. Sample content only.

## Conventions

- Plain semantic HTML5. Real `<label>` elements tied to inputs with `for`,
  `<fieldset>` and `<legend>` for grouped inputs, `<caption>` on tables (use
  `class="visually-hidden"` when it would be redundant on screen).
- Relative paths for all links and stylesheets, so the site works from a file
  path, `python3 -m http.server`, GitHub Pages, and Netlify without changes.
- One folder per tool under `tools/`, containing `index.html`.
- Interface copy is plain and specific. Name things by what the user does, not by
  how the system works. Buttons say what happens: "See recommendations", not
  "Submit".
- Keep each tool page's `Owner` and `Status` metadata block intact. Teams use it
  to claim work.

## Verifying a change

There is no test suite. After editing, check:

```bash
grep -rniE "<script|onclick|onchange|style=" --include="*.html" .
grep -nE "^\s*(color|background|font-family|border|box-shadow)\s*:" css/layout.css
```

Both should return nothing. Then open the page in a browser, or serve it with
`python3 -m http.server 8000`.

## Working with this team

Most people here are educators and curriculum specialists, several of them new
to git. When you explain a change, name the file and say what it does in plain
terms. Skip the framework vocabulary. If a request is ambiguous, ask rather than
picking an interpretation and building it out.
