# Git exercises

Five exercises, in order. About an hour total. Nothing here can break anything.

Each one adds exactly one new idea, and exercises 3 and 4 will *deliberately*
put you into a merge conflict — because the first conflict you hit should be one
somebody set up for you on purpose, not one that lands on a Tuesday afternoon
when something is due.

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
git checkout -b yourname/claim-workshop-builder
```

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

**You learned:** branch, add, commit, push, pull request, merge.

---

## Exercise 3 — Cause a merge conflict on purpose

Everybody does this one at the same time. That is what makes it work.

```
git checkout main
git pull
git checkout -b yourname/add-to-team-list
```

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
which is the whole reason branches exist.
