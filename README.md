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
css/layout.css                      Shared stylesheet. Layout only, no visual styling.
tools/assessment-engine/            Candidate #2
tools/standards-mapper/             Candidate #3a (internal)
tools/standards-lookup/             Candidate #3b
tools/pathway-builder/              Candidate #3c
tools/resource-generator/           Candidate #4
tools/workshop-builder/             Candidate #5
tools/change-impact-tracker/        Candidate #6 (internal)
docs/git-exercises.md               Five exercises, in order
CONTRIBUTING.md                     The short version
```

## The three constraints

These are on purpose. Please keep them until your team decides otherwise.

**No JavaScript.** Not one line, anywhere, right now. Forms point at anchors and
buttons do nothing. Adding behavior is the sprint's work, and it is much more
satisfying to add it to a page that already has real structure.

**No visual styling.** `css/layout.css` handles layout — grids, spacing, widths —
and nothing else. No colors, no fonts, no borders, no shadows. Every page will
look like 1994. That is fine. It means the HTML has to carry the meaning, and it
means your first styling commit produces a visible, obvious win.

**No student data. Ever.** This repository is public. Sample content only, and
the districts and names in it are illustrative.

## Running it locally

There is no build step. Open `index.html` in a browser and it works.

If you would rather serve it (relative paths behave more predictably):

```
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.

## Getting it online

Both of these serve the linked CSS correctly, and neither needs configuration.

**GitHub Pages** — Settings → Pages → Source: Deploy from a branch → `main`, root.
Live in about a minute. Publishes one branch only, so you see changes after merge.

**Netlify, Vercel, or Cloudflare Pages** — connect the repo once, publish
directory `.`, no build command. The reason to prefer one of these: **every pull
request gets its own preview URL**, posted as a comment on the PR. A reviewer
clicks it and sees the change before approving.

That preview link is what makes pull requests feel worth the trouble rather than
like paperwork. If you set up only one thing, set up that.

## Start here

New to git? Work through `docs/git-exercises.md` in order. It takes about an hour
and by the end you will have opened a pull request, resolved a merge conflict,
and reviewed somebody else's work.
