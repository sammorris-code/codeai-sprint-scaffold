# Claude Code exercises

A separate track from the **Git tutorial**. Same repository, different tool.

These start from nothing installed. You do not need to have finished the git
exercises first, though it helps to have opened one pull request by hand before
you watch Claude do it — you will know what it is actually doing.

**If terms like branch, commit, and pull request are new to you**, the **Claude
Desktop tutorial** in the first tab opens by defining them and walks the same
loop without a terminal. It is the gentler way in; this track assumes you are
comfortable at a command line.

Budget about 90 minutes. Work through them in order.

---

## Before you start

**You need a paid Claude account.** Claude Code requires a Pro, Max, Team,
Enterprise, or Console plan. The free Claude.ai plan does not include it. If we
are on a Team plan, you already have access.

**One note about our setup.** The org-level GitHub connector is turned off in our
workspace for student-privacy reasons. That is fine — it is not what these
exercises use. Claude Code runs locally on your own machine against your own
clone of the repository, which is permitted. When you need to open a pull
request, you will use the GitHub website (or the `gh` command line tool if you
have it), not a connector.

**Pick your surface.** Two ways to run Claude Code:

| Surface | Good for | Where it is covered |
|---|---|---|
| **Terminal (CLI)** | People comfortable at a command line | This tutorial |
| **Desktop app** | People who would rather not use a terminal at all | The **Claude Desktop tutorial**, in the first tab |

If you are not a developer and the terminal is unappealing, the desktop app is a
real option and not a lesser one — go to the first tab rather than working
through this track. It covers the same loop with no terminal at all, and starts
from the assumption that you have never used git.

Everything below shows terminal commands, but each has a desktop equivalent, and
the prompts you type to Claude are identical either way.

---

## Exercise 1 — Install it and prove it works

**macOS, Linux, or WSL:**

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**Windows PowerShell:**

```powershell
irm https://claude.ai/install.ps1 | iex
```

Then open a **new** terminal window and check:

```bash
claude --version
```

You should see a version number. If you get `command not found`, that is almost
always because the installer added Claude Code to the path for new shells and you
are still in the old one — open a fresh terminal and try again.

For a fuller check of your install and settings:

```bash
claude doctor
```

Remember `claude doctor`. When something is wrong later, run it before you start
searching.

**You learned:** install, verify, and the one diagnostic worth memorizing.

---

## Exercise 2 — Point it at the repository and ask, don't edit

Get the repository and start a session inside it:

```bash
git clone https://github.com/sammorris-code/codeai-sprint-scaffold
cd codeai-sprint-scaffold
claude
```

The first time you run `claude`, it opens a browser to log you in.

Claude Code is now working in this folder. **This is the whole "connecting to the
repo" step.** There is no configuration, no linking, no connector. It reads the
directory you started it in.

Start by asking, not instructing:

```
What is this repository? Summarize the structure and the constraints.
```

It will read `CLAUDE.md` and the pages and tell you. Then try:

```
Which tool pages have no owner assigned yet?
```

Notice what happened: it searched the files and answered. It did not change
anything. Asking questions about a codebase is the most underused thing Claude
Code does, and it is completely safe.

One more:

```
Explain what css/layout.css is doing, and where CLAUDE.md says to put colors and
fonts instead.
```

**You learned:** starting a session is just `cd` and `claude`. Read-only work is
free and safe.

---

## Exercise 3 — Your first edit, reviewed before it lands

Make a branch first. Claude can do this for you, but do it yourself once so you
know the state you are in:

```bash
git checkout -b yourname/claude-first-edit
claude
```

Then:

```
On the workshop builder page, set the Owner field to my name, [your name].
Also update the matching Owner entry on the portal index page.
```

Claude will show you a diff and ask permission before writing. **Read the diff.**
This is the habit that matters most. Approve it, then:

```
Show me what you changed.
```

Now a slightly larger ask, on your own tool page:

```
Add a section to this page called "Data we would need" listing the data sources
this tool would require. Use the same markup conventions as the rest of the page.
```

Check the result in a browser. Then check that it obeyed the house rules:

```
Does this follow the conventions in CLAUDE.md? Check the markup conventions and
where styling is supposed to live.
```

It will tell you which conventions it followed and where it got them. Notice you
never mentioned that file.

**You learned:** permission prompts, reading diffs, and that the repository's
`CLAUDE.md` is already shaping what Claude does without you mentioning it.

---

## Exercise 4 — Plan before building

For anything bigger than a small edit, get the plan first. Press `Shift+Tab` to
cycle permission modes until you reach plan mode — in plan mode Claude works out
an approach and shows it to you without touching files.

Try this:

```
I want to add an eighth tool page for a District Readiness Checklist, matching
the structure of the existing pages and linked from the portal. Plan it first.
```

Read the plan. Push back on it — that is the point:

```
Skip the sidebar. Keep it to one column like the standards mapper page.
```

Then let it build.

If it goes somewhere you did not want, you have two outs: `/rewind` to undo
Claude's edits, or plain `git checkout .` to throw away everything uncommitted.
Nothing on a branch can hurt `main` — as long as the work is actually on a
branch, which is why you made one first.

**You learned:** plan mode, steering a plan before code exists, and how to back
out.

---

## Exercise 5 — Commit and open a pull request

Still in the session:

```
Commit this with a clear message, then push the branch.
```

Watch what it writes. If the commit message is vague, say so — "make the message
say what changed, not 'updates'" — and it will redo it.

For the pull request, either:

- **The GitHub website.** Push, then GitHub offers a "Compare & pull request"
  button. This always works.
- **The `gh` CLI**, if you have it installed. Then you can ask Claude:
  `Open a pull request for this branch with a description of the change.`

Either way, a human reviews it. Claude opening the PR does not mean Claude
approves the PR.

A bot posts a preview link on the pull request — a copy of the whole site built
from your branch, running, before it merges. Open it and click through to the
page you changed. The diff tells a reviewer what changed; the preview tells them
whether it works.

### After it merges

Once someone approves and merges it, your laptop does not know yet. The merge
happened on GitHub. Back in the session:

```
Switch to main and pull, then confirm my change is there.
```

```
Delete my local copy of the branch that just merged, and clear out any
references to branches that no longer exist on GitHub.
```

GitHub deletes its own copy of the branch automatically when the pull request
merges, so only your local copy and a stale reference are left. If Claude reports
that the branch has unmerged commits, do not force it — that means something on
the branch never reached `main`, and it is worth understanding before you throw
it away.

**You learned:** commits and PRs from inside a session, where the human stays in
the loop, and how to get back to a clean starting point afterwards.

---

## Exercise 6 — Hand it a merge conflict

Do the **Git tutorial** version of this first if you have not — you should see a
conflict raw at least once before you watch it get resolved for you.

Get into a conflict on purpose. Two people both add themselves to the "Who is
working on this" list in `index.html`, one merges, the other pulls:

```bash
git checkout main
git pull
git checkout yourname/your-branch
git merge main
```

When git stops with a conflict, start Claude and ask:

```
There is a merge conflict in index.html. Show me what the two sides are, explain
what each one changed, then resolve it keeping both names in alphabetical order.
```

Read the explanation before you accept the fix. The explanation is the valuable
part — after two or three of these you will be able to resolve them yourself, and
you will know when Claude's resolution is wrong.

Then:

```
Commit the resolution and push.
```

**You learned:** conflicts are a normal thing to hand to Claude, and the
explanation is worth more than the fix.

---

## Exercise 7 — Teach the repository something

This is the exercise that compounds. `CLAUDE.md` is a plain markdown file at the
repository root that Claude Code reads at the start of every session in this
folder. It is why Claude already knew this page's conventions in exercise 3
without you explaining them.

Open it and read it:

```
/memory
```

That lists the instruction files and lets you open them. To see what actually
loaded in the current session:

```
/context
```

Now add something real. Find a correction you had to give Claude during these
exercises — something you would otherwise have to repeat next session — and ask
for it to be written down:

```
Add to CLAUDE.md: [the rule you keep having to explain]
```

Then commit that change and open a pull request for it, because `CLAUDE.md` is
shared. Everyone's sessions get better when one person writes down a lesson.

### Content hygiene for CLAUDE.md

This matters more for us than for most teams, because this repository is public
and because we work near student data.

- **Never** put student information, real district contacts, credentials, API
  keys, or internal pricing in `CLAUDE.md`. It is committed, it is public, and it
  is loaded into context every session.
- Keep it short. Aim well under 200 lines. Long instruction files get followed
  less reliably, not more.
- Write rules you could check. "Buttons say what happens, not 'Submit'" is
  verifiable. "Write good copy" is not.
- Add a rule when you have explained the same thing twice. Not before.
- If two rules contradict each other, Claude may pick either one. Read the file
  end to end occasionally.

For personal notes you do not want committed, use `CLAUDE.local.md` and add it to
`.gitignore`.

Separately, Claude Code keeps its own automatic notes per repository on your
machine — you can browse or turn those off from `/memory`. Those are local to
you and are not committed.

**You learned:** the file that makes every future session better, and the rules
for keeping it safe and useful.

---

## The short version

```
claude                  start a session in the current folder
claude doctor           diagnose a broken install
Shift+Tab               cycle permission modes, including plan mode
/rewind                 undo Claude's edits
/memory                 view and edit instruction files
/context                see what actually loaded this session
/init                   generate a starting CLAUDE.md in a new repo
```

Four habits that separate people who get value from this from people who do not:

1. **Ask before instructing.** Questions about a codebase are free.
2. **Read the diff.** Every time. This is the whole safety model.
3. **Plan before anything nontrivial.** Steering a plan is cheaper than undoing
   code.
4. **Write down corrections.** If you explained it twice, it belongs in
   `CLAUDE.md`.

## Where the real documentation is

- Setup and system requirements: https://code.claude.com/docs/en/setup
- Quickstart: https://code.claude.com/docs/en/quickstart
- Desktop app: https://code.claude.com/docs/en/desktop-quickstart
- CLAUDE.md and memory: https://code.claude.com/docs/en/memory
- Common workflows: https://code.claude.com/docs/en/common-workflows
