# Git basics in Claude Desktop

A standalone tutorial. It assumes Claude Desktop is already installed and that
you have **never used git**. You will not need a terminal, though there is one
available if you get curious.

By the end you will have changed a real repository, had your change reviewed by a
colleague, resolved a conflict with someone else's edit, and reviewed their work
in turn. About 75 minutes.

You need a paid Claude plan (Pro, Max, Team, or Enterprise) for the Code tab to
work. If we are on a Team plan, you already have it.

---

## Six words, before you touch anything

Git has a reputation for being confusing, and most of that comes from people
using the tool before anyone told them what the words mean. There are six. They
take three minutes.

**Repository** — a folder of files that keeps its whole history. Every version of
every file, forever. Ours holds a small website. People say "repo."

**Clone** — your own complete copy of the repository, on your computer. Not a
checkout, not a partial download. Everyone on the team has their own full copy,
and they only differ until someone syncs.

**Branch** — a private workspace inside your copy where you can change things
without affecting anyone. The main branch is called `main`. You never work
directly on `main`; you make a branch, work there, and propose it back. A branch
is cheap and disposable, and nothing you do on one can damage `main`.

**Commit** — a saved checkpoint with a note explaining what changed. Not "save
file" — you save files normally, then gather those saved changes into a commit
when they add up to something describable.

**Pull** — to bring commits down from GitHub into your copy. "Pull the latest"
means "go and get everything the team has merged, and put it in my folder." Its
opposite is **push**, which sends your commits up. Pull down, push up.

**Pull request** — the proposal, and the name deserves unpacking, because it is
the single most confusing term in git. It is *not* a request for you to pull
something. You are asking the repository to pull *your* branch in: "here are my
commits, please look at them, and if they seem right, pull them into `main`."
The request is aimed at `main`, and you are the one making the offer.

If "change request" feels like the more natural name, your instinct is sound —
GitLab, a competing product, calls the identical thing a **merge request**. GitHub
named it after the operation happening underneath, not after what you are asking
for. Everyone says "PR."

This is where the collaboration actually happens. Everything before it is just
you working.

---

## The loop

Those six words are the vocabulary. This is the order you use them in. Every
piece of work you ever do in this repository is one trip down this table.

| Step | What it actually does |
|---|---|
| **pull** | Bring down everything the team has merged since you last looked. You start from the current version of the site instead of last week's. |
| **branch** | Make yourself a named private workspace. Nothing you do in it can affect `main` or anybody else. |
| **change** | Edit the files. In Desktop, this is you describing what you want and reading the diff Claude offers back. |
| **commit** | Save a checkpoint with a note explaining what changed. Still only on your computer. |
| **push** | Send your commits up to GitHub, so the team can see your branch. |
| **pull request** | Ask for your branch to be pulled into `main`. A human reads it and decides. |
| **merge** | Your commits become part of `main`. The change is now everyone's. |
| **pull** | Merging happened on GitHub, not on your laptop. Pull again to bring the new `main` down to you — and you are back at the top of the table. |

Two things worth noticing before you start.

**Pull appears twice**, at the top and the bottom, and it is the same command
both times. That is what makes this a loop rather than a list. Skipping the pull
at the top is the most common cause of the conflicts you will meet in exercise 6;
skipping the one at the bottom is why people end up wondering where their own
merged work went.

**Only two steps involve anyone else** — the pull request and the merge.
Everything else is you, alone, unable to break anything.

The seven exercises below walk this loop once at a comfortable pace, then run it
again with a deliberate conflict in the middle, then put you on the other side of
it as the person doing the reviewing.

---

## Exercise 1 — Get the repository open

Open Claude Desktop and click the **Code** tab at the top center. Choose
**Local** — that means Claude works with the real files on your machine. Click
**Select folder** and pick the folder where you keep projects (Documents is
fine). Not the repository itself yet, since you do not have it.

Now type this into the session, replacing the URL with the one for our repo:

```
Clone [https://github.com/OUR-ORG/codeai-sprint-scaffold](https://github.com/sammorris-code/codeai-sprint-scaffold) into this folder,
then tell me what you did.
```

Claude will ask permission to run a command. Say yes. It will create a folder
called `codeai-sprint-scaffold` containing your clone.

Now point Desktop at that folder specifically: **Select folder** again, and this
time choose the new `codeai-sprint-scaffold` folder. Everything from here happens
inside it.

Ask a few questions before changing anything. Asking is free and cannot break
anything:

```
What is this repository? Summarize the structure.
```

```
Which tool pages have no owner assigned yet?
```

```
Explain what css/layout.css does, and where CLAUDE.md says colors and fonts
should go instead.
```

Notice that Claude already knows the conventions of this project — where styling
belongs, and that no student data goes anywhere near it. That is because the
repository contains a file called `CLAUDE.md` that Claude reads at the start of
every session here. You did not have to explain any of it.

> **Something to know about this repo:** the pages look plain because the
> scaffold was built structure first, with styling and JavaScript deliberately
> left out until the shape was right. That baseline is finished and those
> restrictions are lifted, so the plainness is unfinished work rather than a
> rule. Leave it alone for now anyway — you are here to learn git, and a styling
> change makes for a messier first pull request.

**You have:** a clone, a session pointed at it, and a sense of what is in it.

---

## Exercise 2 — Make a branch and change one thing

First, the habit that prevents most problems:

```
Switch to main and pull the latest changes, then tell me if anything came down.
```

You do this **before starting any new work**, every time. Your teammates have
been merging their own changes; pulling first means you build on top of their
work instead of alongside it. Skipping this step is the single most common cause
of the conflicts you will meet in exercise 6.

Now make your workspace:

```
Create a branch called yourname/claim-a-tool and switch to it.
```

Use your actual name. You are now in a private workspace. Nothing you do here
touches `main` or anyone else.

Pick a tool page from `tools/` that nobody has claimed and put your name on it:

```
On the workshop builder page, change the Owner field from "unassigned" to my
name, [your name]. Make the same change to that tool's entry on the portal
index page.
```

**Claude will show you a diff before it writes anything. Read it.** Red lines are
being removed, green lines added. This is the most important habit in this whole
tutorial — the diff is your review, and it happens before the change exists.

Approve it. Then look at your work in a browser: find `index.html` in the
repository folder and open it. Click through to the page you claimed. Your name
should be there.

**You have:** a branch, and one real change sitting in it, unsaved to history.

---

## Exercise 3 — Commit it

Your change exists as a modified file. It is not yet in the repository's history,
and it is not yet anywhere but your machine. Two separate steps.

```
What files have I changed? Show me the status.
```

Then:

```
Commit this with a message describing what changed, then push the branch.
```

Watch the message it writes. If it is vague, push back — "make the message say
what changed, not 'updates'" — and it will redo it. A commit message is written
for the person who reads it in six months, which is usually you.

Two things just happened, and they are worth separating:

- **Commit** recorded the change in your local history. Still only on your
  computer.
- **Push** sent your branch to GitHub, where your team can see it.

If you push and nothing appears on GitHub, you committed but did not push. That
is the most common confusion in the first week.

**You have:** a change saved in history and visible to your team, on a branch.

---

## Exercise 4 — Propose it

The change is on GitHub but it is not in `main`. It needs a human to agree.

```
Open a pull request for this branch with a short description of the change.
```

If Claude cannot open it directly, it will tell you — in that case go to the
repository on github.com and click the **Compare & pull request** button that
appears after a push.

Desktop may show you a **PR monitoring panel** with CI status and toggles for
auto-fix and auto-merge. That panel is a *monitor*, not a merge button. Leave the
toggles alone: auto-merge would skip the review step, which is the part you are
here to learn. There is a small external-link icon on the panel that opens the
PR on GitHub, which is where you want to be.

Now go ask an actual colleague to review it. Their side of that is exercise 7.

**You have:** a proposal waiting on a human.

---

## Exercise 5 — Merge, then catch your computer up

Once someone approves it, click **Merge pull request** on GitHub. Your change is
now part of `main`.

Here is the part everybody forgets: **your computer does not know yet.** Merging
happened on GitHub. Your local copy is still sitting on your branch, and your
local `main` is still the old version.

```
Switch to main and pull, then confirm my change is there.
```

Optional tidying, now that the branch has served its purpose:

```
Delete the branch I just merged, locally and on GitHub.
```

**You have:** completed the entire loop once. Everything after this is variations
and problems.

---

## Exercise 6 — Two people, one file, on purpose

Everyone does this at the same time. That is what makes it work, and it is worth
scheduling as a group for fifteen minutes.

Conflicts happen when two people change the same lines of the same file. Git
cannot tell whose version is right, so it stops and asks. The first conflict you
meet should be one someone set up for you deliberately, not one that lands on a
Tuesday when something is due.

Everyone, at the same time:

```
Switch to main, pull, then create a branch called yourname/add-to-team-list.
```

```
In index.html there is a "Who is working on this" list. Add a line for me,
[your name], with what I'm working on, in alphabetical order by first name.
```

Then commit, push, and open a pull request — but **do not merge yet.** Wait until
several people have theirs open.

Now one person merges. Everyone else's pull request will suddenly say *This
branch has conflicts that must be resolved.*

If that is you:

```
Bring main into my branch, and show me the conflict.
```

Before you let Claude fix it, ask it to teach you:

```
Show me exactly what the conflict markers look like and explain what each side
changed. Don't fix it yet.
```

You will see something like this in the file:

```
<<<<<<< HEAD
<li>Alicia — workshop builder</li>
=======
<li>Banks — pathway builder</li>
>>>>>>> main
```

Git is not asking who wins. It is saying *two people changed these same lines and
I will not guess.* In this case you want both names. Now:

```
Resolve it by keeping both names in alphabetical order, then commit and push.
```

The conflict warning on your pull request clears. Merge it.

**You have:** met a conflict, understood what it actually is, and resolved it. It
is an editing task, not an emergency.

---

## Exercise 7 — Review somebody else's work

Reviewing is half of collaboration and it is the half people skip.

Find an open pull request that is not yours, on GitHub. Open the **Files changed**
tab. Green was added, red was removed. Hover over any line and click the blue `+`
to leave a comment on that exact line.

Leave one real comment. A question counts — "what does this field do?" is a
useful review comment. Then click **Approve**.

Approving is low-stakes. You are not certifying the code is perfect. You are
saying it should go in.

If our repository is connected to Netlify or Vercel, there is a preview link in
the pull request comments. Click it: you are looking at their version of the site
running, before it merges. That is the thing that makes this whole ceremony feel
worth the trouble rather than like paperwork.

You can also bring the branch onto your own machine to poke at it:

```
Check out the branch from pull request #4 so I can look at it locally.
```

**You have:** done the other half of the job.

---

## Habits worth keeping

1. **Pull before you branch.** Every time. Prevents most conflicts.
2. **Read the diff before approving.** Every time. This is the safety model.
3. **Ask Claude to explain, not just to do.** "Show me what changed and why" costs
   you five seconds and is how you stop needing this tutorial.
4. **Never work on `main`.** Branch for everything, even a one-word fix. `main`
   is where finished work lands, not where work happens.
5. **One PR, one idea.** Small pull requests get reviewed. Large ones get
   approved without being read, which is worse than not being reviewed at all.

## If you want to see the real commands

Everything above ran actual git commands underneath. You can watch them, or run
them yourself, in Desktop's built-in terminal — press **Ctrl+`** to open it.

These four cover most of it:

```
git status                  where am I, what have I changed
git pull                    get everyone else's work
git checkout -b name        start a new branch
git add . && git commit     save a checkpoint
```

Try `git status` after making a change. Then ask Claude what the output means.
Reading git's own words with a translator next to you is a fast way to stop
finding it opaque.

## Glossary

| Word | Means |
|---|---|
| repository, repo | a folder that keeps its full history |
| clone | your own complete copy of it |
| `main` | the branch holding the agreed-upon version |
| branch | your private workspace |
| commit | a saved checkpoint with a note |
| push | send your commits to GitHub |
| pull | bring GitHub's commits to you |
| pull request, PR | a proposal to merge your branch |
| merge | fold a branch into another |
| conflict | two people changed the same lines; git wants a decision |
| diff | the display of what was added and removed |

## Where to go next

- **`git-exercises.md`** — the same loop typed by hand, no Claude. Worth doing
  once. Understanding what the tool does for you is what lets you fix it when it
  goes sideways.
- **`claude-code-exercises.md`** — the terminal version of Claude Code, plus plan
  mode, permission modes, and how to teach the repository new rules through
  `CLAUDE.md`.
- **`../CONTRIBUTING.md`** — the short reference for this repo once you no longer
  need a tutorial.
