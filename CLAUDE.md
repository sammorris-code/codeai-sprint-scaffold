# CLAUDE.md

Project instructions for Claude Code. Read this before editing anything here.

## What this repository is

A deliberately primitive multi-page static website. It has two jobs: it is a
practice ground for a team learning git and Claude Code, and it is the starting
scaffold for a three-day product sprint. It is **not** a production site.

The seven pages under `tools/` each correspond to one candidate product from the
sprint's scoping work. `index.html` is the portal directory that links them.

## Hard constraint

One rule is absolute:

- **This repository is public.** No student data, no real district contacts, no
  credentials, no internal pricing. Sample content only.

## Building on the scaffold

This repository used to ban JavaScript and visual styling. **Those bans are
lifted.** The baseline is live and teams are building on it now, so JavaScript,
CSS, frameworks, and build tooling are all available. Do not refuse a request,
or strip working code, on the grounds that this is a "no JavaScript" repository.
It is not one any more.

What replaces the bans is ordinary judgment:

- **Pages currently open straight from a file path.** Anything using `fetch()`,
  ES modules, or a service worker will not run from `file://` and needs a served
  site. That is a fine trade to make — just say so, and give the page a real
  fallback rather than an empty panel.
- **A build step is a decision, not a detail.** `netlify.toml` publishes `.` with
  no build command, and GitHub Pages serves the branch root. A toolchain means
  changing both and handing the team an install step they did not have before.
  Worth doing deliberately; not worth acquiring by accident for one convenience.
- **Shared files still collide.** `index.html` and `css/layout.css` are touched
  by everyone. Keep changes to them small and separate from other work.
- **Per-tool work belongs in the tool's folder** — `tools/<name>/style.css` and
  any scripts alongside it, linked from that page's `<head>`, where a
  commented-out `<link>` is already waiting. This is merge hygiene now, not a
  rule.
- **Site-wide visual styling is fine.** Prefer adding `css/theme.css` to growing
  `layout.css`, so the file every page depends on stays small and stable.
- **Keep the semantics and the keyboard working.** Anything interactive must be
  reachable by tab and operable by keyboard, and real controls (`<button>`,
  `<a>`, `<details>`) beat a `div` with a click handler. This team builds for
  school districts, so accessibility is part of the work, not a later pass.

## Conventions

- Plain semantic HTML5. Real `<label>` elements tied to inputs with `for`,
  `<fieldset>` and `<legend>` for grouped inputs, `<caption>` on tables (use
  `class="visually-hidden"` when it would be redundant on screen).
- Relative paths for all links and stylesheets, so the site works from a file
  path, a local static server, GitHub Pages, and Netlify without changes.
- One folder per tool under `tools/`, containing `index.html`.
- Interface copy is plain and specific. Name things by what the user does, not by
  how the system works. Buttons say what happens: "See recommendations", not
  "Submit".
- Keep each tool page's `Owner` and `Status` metadata block intact. Teams use it
  to claim work.

## Verifying a change

There is no test suite and nothing to install. Open the page in a browser from
its file path — every page except `tutorials/` works that way, and that is how
the team looks at their own work.

There is no build step. If a page you are working on genuinely needs to be
served, any static server will do; do not add a toolchain to the project for it.

Then tab through anything interactive to confirm it is reachable and operable by
keyboard, and check the browser console for errors. The `grep` checks that used
to live here enforced the JavaScript and styling bans, and went with them.

## Working with this team

Most people here are educators and curriculum specialists, several of them new
to git. When you explain a change, name the file and say what it does in plain
terms. Skip the framework vocabulary. If a request is ambiguous, ask rather than
picking an interpretation and building it out.
