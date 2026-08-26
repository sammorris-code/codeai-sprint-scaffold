# Git exercises

Five exercises, in order. About an hour total. Nothing here can break anything.

Each one adds exactly one new idea, and exercises 3 and 4 will *deliberately*
put you into a merge conflict — because the first conflict you hit should be one
somebody set up for you on purpose, not one that lands on a Tuesday afternoon
when something is due.

---

## Before you start anything

Every time you sit down to work — exercise 2 onward, and every real task after
that — do these two things in this order:

```
git checkout main
git pull                            get everyone else's merged work
git checkout -b yourname/what-it-does
```

Pull first, branch second. The reason is that a branch is a copy of whatever
`main` looked like at the moment you created it. If you branched on Monday and it
is now Thursday, you are editing Monday's version of the site — and everything
your teammates merged in between is missing from your copy. That gap is where
most avoidable conflicts come from. Pulling first means your branch starts from
what everyone has agreed on, so the only things you can conflict with are changes
made while you were actually working.

Thirty seconds at the start. It is the single highest-value habit on this list.

## After a merge

Once your pull request is merged on GitHub, your branch has done its job. Get
back to a clean starting point:

```
git checkout main
git pull                            bring your merged work down into main
git fetch --prune                   forget branches that no longer exist on GitHub
git branch -d yourname/what-it-does delete your local copy of the finished branch
```

The `pull` matters because merging happened on GitHub, not on your laptop — until
you pull, your local `main` does not contain your own merged work, let alone
anyone else's. `--prune` clears out remote-tracking references to branches GitHub
already deleted, so `git branch -a` keeps showing you real branches instead of
ghosts. If `git branch -d` refuses, it is telling you the branch has commits that
never made it into `main` — worth a look before you force it.

Then you are back at the block above, ready to pull and branch again.

---

## Exercise 1 — Get the repository and look around

```
git clone <repo-url>
cd codeai-sprint-scaffold
```

Open `index.html` in a browser. Click into a couple of tool pages. It is ugly.
That is intentional.

```
git log --oneline
git status
```

`git log` is the history. `git status` is your most useful command — it tells you
where you are and what you have changed. When you are confused, run it.

**You learned:** clone, log, status.

---

## Exercise 2 — Claim a tool

This one touches a file nobody else is touching, so it will merge cleanly. The
point is to complete the whole loop once without friction.

```
git checkout main
git pull
git checkout -b yourname/claim-workshop-builder
```

That is the "Before you start anything" block above. You just cloned, so the pull
will report *Already up to date* — run it anyway, so the habit is attached to
starting work rather than to remembering.

Open your tool's `index.html`. Find this near the top:

```html
<dt>Owner</dt><dd>unassigned</dd>
```

Put your name in place of `unassigned`. Then:

```
git add .
git commit -m "Claim workshop builder"
git push -u origin yourname/claim-workshop-builder
```

Go to GitHub. It will offer to open a pull request. Open it. Ask someone to
approve it. Merge it.

Then run the "After a merge" block above. Your first merged branch is the easiest
possible place to practice cleaning up after one.

**You learned:** branch, add, commit, push, pull request, merge.

---

## Exercise 3 — Cause a merge conflict on purpose

Everybody does this one at the same time. That is what makes it work.

```
git checkout main
git pull
git checkout -b yourname/add-to-team-list
```

Same three lines as last time. This is the pull that matters — if you skip it,
you branch from a version of `index.html` that is missing the name someone merged
five minutes ago, and you have manufactured a conflict before you have typed
anything.

In `index.html`, find the "Who is working on this" list. Add one line for
yourself, in alphabetical order by first name:

```html
<li>Alicia — workshop builder</li>
```

Commit, push, open a pull request. **Do not merge yet.** Wait until two or three
other people have opened theirs.

Now one person merges. Everyone else's pull request will show
*This branch has conflicts that must be resolved.*

To fix yours:

```
git checkout main
git pull
git checkout yourname/add-to-team-list
git merge main
```

Git will stop and mark the conflict inside `index.html`:

```
<<<<<<< HEAD
<li>Alicia — workshop builder</li>
=======
<li>Banks — pathway builder</li>
>>>>>>> main
```

Git is not asking who wins. It is saying *two people changed the same lines and I
will not guess.* You want both names, so delete the three marker lines and keep
both `<li>` lines in alphabetical order. Then:

```
git add index.html
git commit
git push
```

The conflict warning on your pull request clears. Merge it.

**You learned:** what a conflict actually is, and that resolving one is editing a
file — not an emergency.

---

## Exercise 4 — Make it not ugly

Now the shared stylesheet, which is the other place conflicts live.

Open `css/layout.css` and scroll to the bottom. There is a commented-out block
that puts a bottom border on table rows. Uncomment it, reload a page with a
table, and see the tables become readable.

Then add one more rule of your own. A `font-family` on `body` is a good one — it
changes every page at once, which shows you what a shared file *means*.

Same loop: branch, commit, push, pull request. If someone else edited the same
region of the file, you will conflict again. You know how to handle that now.

**You learned:** why we keep shared files small, and why your tool's own
`style.css` is the safer place for most work.

---

## Exercise 5 — Review someone else's work

Find an open pull request that is not yours.

Open the **Files changed** tab. Green lines were added, red lines removed. Hover
a line and click the blue `+` to leave a comment on that exact line.

Leave one real comment — a question counts. Then approve it.

If the repo is connected to Netlify or Vercel, there is a preview link in the
pull request comments. Click it. You are looking at their version of the site,
running, before it merges. This is the part that makes the whole ceremony worth
it.

**You learned:** review, line comments, preview deploys.

---

## The four commands you will actually use

```
git status                  where am I, what have I changed
git pull                    get everyone else's work
git checkout -b name        start something new
git add . && git commit     save it
```

Everything else you can look up. And nothing you do on a branch can hurt `main`,
which is the whole reason branches exist — as long as the work is actually on a
branch. `CONTRIBUTING.md` explains what goes wrong when it is not.

---

## Next

`claude-code-exercises.md` covers the same repository through Claude Code,
starting from nothing installed. Having done the exercises above by hand, you
will be able to tell what it is doing for you — including exercise 6, where you
hand it a merge conflict just like the one you resolved in exercise 3.
