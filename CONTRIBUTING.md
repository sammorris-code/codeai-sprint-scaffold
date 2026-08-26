# Contributing

The short version. For practice exercises see `docs/git-exercises.md`.

## The loop

```
git checkout main                   start from the shared version
git pull                            get everyone else's merged work
git checkout -b your-branch-name    make your own branch
...edit files...
git add .
git commit -m "what you did"
git push -u origin your-branch-name
```

Then open a pull request on GitHub. Someone reviews it. It merges.

Pull first, branch second, every time — a branch is a copy of `main` as it looked
when you made it, so branching from a stale `main` means editing a stale site.
After the merge, `git checkout main && git pull` brings the merged work down to
your laptop; `docs/git-exercises.md` has the full before-and-after routine.

## Branch names

`yourname/what-it-does` works fine. `alicia/style-workshop-builder`,
`banks/pathway-time-chart`.

Avoid working directly on `main`. Not because a commit there is destructive — it
is not — but because `main` is the one copy everybody pulls from, and a commit
sitting on your local `main` is invisible to everyone until you push it, and
unreviewable once you do. It also breaks `git pull`: the moment your `main` and
GitHub's `main` both have commits the other lacks, `pull` stops and demands you
choose how to reconcile them, which is a decision nobody should have to make
before they can get their teammates' work. Branch for everything, and `main`
stays what it should be — a landing spot for reviewed work, never a workspace.

## Commit messages

Say what changed, in the present tense, in one line. "Add time constraint chart
to pathway builder" tells a reader something. "updates" and "fix" do not.

## Which files to touch

**Your own tool folder** — go ahead, it is yours. Add pages, add a `style.css`,
restructure the markup.

**`index.html` and `css/layout.css`** — shared by everyone. Expect conflicts, and
pull before you start. Keep changes to these small and separate from your other
work so they are easy to review and easy to merge.

## Styling

When your team starts styling, create `style.css` inside your own tool folder and
uncomment the link tag already sitting in your page's `<head>`. Please do not put
colors or fonts into `css/layout.css` — it is shared, and it is the file most
likely to cause a painful conflict.

## Reviewing a pull request

Look at the Files changed tab. Click the preview link if the repo is wired to
Netlify or Vercel. Leave a comment on a specific line if something looks off.
Approving is a normal, low-stakes thing to do — you are not certifying the code
is perfect, only that it should go in.

## If you use Claude Code

`CLAUDE.md` at the repository root tells Claude Code the house rules for this
project — no JavaScript, no visual styling in the shared stylesheet, no student
data. It is read automatically at the start of every session in this folder, so
you do not need to re-explain the constraints each time.

If you find yourself correcting Claude on the same thing twice, add it to
`CLAUDE.md` and open a pull request. That file is shared, and everybody's
sessions improve when one person writes down a lesson.

New to the tool? `docs/claude-code-exercises.md` starts from installation.
