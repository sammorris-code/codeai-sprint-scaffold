# CodeAI Sprint Scaffold

A deliberately plain, deliberately unfinished website. Two jobs:

1. **A git on-ramp.** A place for the team to practice branching, pull requests,
   review, and merge conflicts on something where nothing can break.
2. **A starting point for the Phoenix sprint.** Seven tool pages, one per
   candidate product, with the structure already in place so sub-teams spend
   three days on the build instead of on scaffolding.

## What is here

```
index.html                          District Implementation Portal — the directory
css/layout.css                      Shared stylesheet. Structure; shared by every page.
tools/assessment-engine/            Candidate #2
tools/standards-mapper/             Candidate #3a (internal)
tools/standards-lookup/             Candidate #3b
tools/pathway-builder/              Candidate #3c
tools/resource-generator/           Candidate #4
tools/workshop-builder/             Candidate #5
tools/change-impact-tracker/        Candidate #6 (internal)
CLAUDE.md                           Project instructions for Claude Code sessions
docs/git-exercises.md               Track 1: five git exercises, in order
docs/claude-code-exercises.md       Track 2: seven Claude Code exercises, in order
docs/claude-desktop-tutorial.md     Track 3: git in Claude Desktop, no terminal
tutorials/                          All three tracks as a web page, at /tutorials/
CONTRIBUTING.md                     The short version
```

## Three learning tracks

**Read them here — this is the link to hand people:**

**https://web.samandjt.us/github/tutorials/**

That page renders the three markdown files below as tabs. The files in `docs/`
are the source; the page is how anyone actually reads them. Do not send people
the `.md` files.

They are independent and can be done in any order.

**`docs/claude-desktop-tutorial.md`** — the whole loop in Claude Desktop, with no
terminal at all. About 75 minutes. Assumes you have never used git and starts by
defining the six words. **Start here** unless you have a reason not to.

**`docs/git-exercises.md`** — git by hand, in a terminal. Branch, commit, pull
request, merge conflict, review. About an hour. Worth doing once to understand
what the tools are doing for you.

**`docs/claude-code-exercises.md`** — the same repository through Claude Code in
a terminal, starting from nothing installed. About 90 minutes, and it goes
further: plan mode, permission modes, and teaching the repo new rules through
`CLAUDE.md`.

## The one constraint

**No student data. Ever.** This repository is public. Sample content only, and
the districts and names in it are illustrative. No real district contacts, no
credentials, no internal pricing.

That is the whole list now.

## What the scaffold started as

The baseline was built with two extra restrictions — no JavaScript and no visual
styling — so that the structure came first and the HTML had to carry the meaning
on its own. **Both are lifted.** The baseline is live, and JavaScript, CSS,
frameworks, and build tooling are all open to you.

Two consequences worth knowing before you use them:

- **Pages currently open straight from a file path.** Anything using `fetch()`
  or ES modules will not run from `file://` — it needs a served site. Not a
  reason to avoid it, just a thing to know when a teammate says "it's blank."
- **A build step changes how the site deploys.** Right now the workflows in
  `.github/workflows/` copy files to the `gh-pages` branch and run no build
  command. Adding a toolchain means updating both of them and giving everyone an
  install step. Worth doing on purpose; not worth acquiring by accident.

You will still find leftover pages with buttons that do nothing and forms
pointing at `#` anchors. Those are unfinished, not protected — wire them up.

## Running it locally

There is no build step and nothing to install. Open `index.html` in a browser
and it works. Edit a tool page, reload the tab, see the change.

The one exception is `/tutorials/`, which builds itself from the files in
`docs/` at runtime and therefore only works served. Read it at
**https://web.samandjt.us/github/tutorials/** rather than locally.

## Where it is online

The site is published by GitHub Pages, from the `gh-pages` branch, by the
workflows in `.github/workflows/`. Nothing to configure and no third-party
account.

**The live site** — https://sammorris-code.github.io/codeai-sprint-scaffold/

Updated automatically about a minute after anything merges to `main`.

**Every pull request gets its own preview**, at a URL like:

```
https://sammorris-code.github.io/codeai-sprint-scaffold/pr-preview/pr-42/
```

A bot posts that link as a comment on the pull request, updates it every time
you push, and deletes the preview when the pull request closes. A reviewer
clicks it and sees the change running before approving.

That preview link is what makes pull requests feel worth the trouble rather than
like paperwork.

### How the two workflows fit together

`deploy-site.yml` publishes `main` to the root of `gh-pages`. `pr-preview.yml`
publishes each pull request to `pr-preview/pr-<number>/` on that same branch.
The deploy job deliberately leaves `pr-preview/` alone while replacing the site,
so publishing `main` never breaks a preview link on an open pull request.

Because both write to the same branch, they share one concurrency group and
queue rather than run together. They also wait for GitHub's own Pages
deployment to finish before pushing.

Tearing a preview down is split by outcome, which is the non-obvious part. A
pull request **closed without merging** is cleaned up by `pr-preview.yml`,
because nothing else will run. A **merged** one is cleaned up by
`deploy-site.yml`, which drops the previews of any pull requests no longer open
while it publishes.

That split exists so a merge causes exactly **one** push to `gh-pages`. When
both workflows pushed — which is how this was first written — the two Pages
deployments raced, the second failed with *"in progress deployment"*, and the
live site quietly served stale content until somebody noticed.

All of it relies on every path in the site being relative, which is why a
preview works from a deep subdirectory without a single link being changed.

## Start here

New to git? Work through `docs/git-exercises.md` in order. It takes about an hour
and by the end you will have opened a pull request, resolved a merge conflict,
and reviewed somebody else's work.
