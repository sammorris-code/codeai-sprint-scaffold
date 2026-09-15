# Build the review queue

This is a brief for one piece of work: the main screen of the Standards Mapper.
Everything you need is already in this repository. You do not need a database, an
API, a login, or anything from the Standards team to start.

Read this once, then start. Ask about anything that is not clear here rather than
guessing, because a guess in this screen becomes a wrong claim to a school
district later.

---

## 1. What you are building

A person is checking a list of proposed matches between a **standard** (something
a state says must be taught) and a **lesson** in one of our courses. A tool
proposed each match. The person decides whether it is real.

Your screen is where they do that.

**Build a queue, not a table.** The public site already shows finished results as
a sortable table, so a table here would be the wrong shape twice over. What this
screen needs is a person's judgement on one thing at a time, with the proof in
front of them and Accept or Reject beside it.

The table on the page now is a placeholder. Replace it.

---

## 2. Start here

```bash
git clone <this repository>
cd codeai-sprint-scaffold
git checkout -b <your-name>/review-queue
python3 -m http.server 8000
```

Then open <http://localhost:8000/tools/standards-mapper/>.

**You must serve the page. Do not open it by double-clicking.** A browser will
not let a page read data files from a file path. The page already explains this
on screen if you forget.

Work in `tools/standards-mapper/`. Everything you write goes there:

```
tools/standards-mapper/
  index.html     the page
  style.css      your styles. It is already linked.
  loader.js      reads the data. Already written. Use it, do not replace it.
  mapper.js      fills the two menus at the top. Already written.
  queue.js       YOUR FILE. Create it.
```

Add `<script src="queue.js"></script>` after the other two in `index.html`.

---

## 3. The data

Read it with the loader that already exists:

```js
window.StandardsSource.load('review-queue')
  .then(function (data) { /* data.items is your queue */ })
  .catch(function (error) { /* error.kind is 'file-path', 'not-found' or 'network' */ });
```

You will need to add `'review-queue'` and `'run'` to the `paths` list in
`loader.js`. That is a two-line change and it is the only reason to open that
file.

The data is invented. It has the exact shape the real API will return, so when
the API exists somebody changes one line in `loader.js` and your screen keeps
working. You can also read the files directly to see what you are dealing with:

- `contract/fixtures/review-queue.json` — the queue. Start here.
- `contract/fixtures/run.json` — the counts for the header.
- `contract/fixtures/standards-sets.json` — which set is being reviewed.

`contract/api.md` describes every field. `contract/README.md` explains the rules.

### The shape, in short

`review-queue.json` has an `items` array. **One item is one standard.** Each item
holds:

| Field | What it is |
|---|---|
| `standard` | The standard itself. `identifier`, `statement`, `concept`. |
| `standard.boundary_includes` | What counts as teaching it. |
| `standard.boundary_excludes` | What does not count. This is what catches a wrong match. |
| `outcome.outcome` | The verdict for the whole standard. One of six values. |
| `outcome.in_scope` | False means this standard was never in the running. |
| `records` | The lessons proposed as evidence. **May be empty.** |

One record is one lesson offered as proof:

| Field | What it is |
|---|---|
| `lesson.lesson_name` | The lesson's title. **Show this.** |
| `lesson.unit_name`, `lesson.displayed_number` | Where it sits. |
| `level` | How deeply this lesson covers it: introduced, developed, mastered. |
| `evidence` | The actual student task. This is the proof. Give it room. |
| `note` | A caveat the reviewer needs. Never hide it. |
| `flags` | Warnings. See below. |
| `review_status` | proposed, accepted, rejected, changed, or stale. |

### The flags

There is deliberately **no confidence score**. A number invites a reviewer to
trust it. Two named warnings replace it, and each one says where to look:

- `depth_doubt` — "Lesson may not go deep enough"
- `weak_match` — "Close match, likely not a real one"
- `overclaim` — "This lesson carries many standards"
- `artifact_mismatch` — "The standard asks for a different artifact"

**Print `flag.label`, never `flag.kind`.** The label is the words a person reads.
`flag.detail` says what to check.

---

## 4. The eleven cases you must handle

The fixtures are not a happy path. Each one carries a case that has already
caused a wrong claim in real work. **A screen that handles all eleven will
survive real data.** Walk through them deliberately.

1. **Four standards have no records at all.** They are still in the queue. A
   screen that loops over records and draws a card per record will silently drop
   them, and the totals will not add up. Loop over `items`.
2. **`outcome.in_scope` is false on two standards.** They are not gaps. They were
   never in the running. Show them differently, or filter them out — but never
   count them as a shortcoming.
3. **`DEMO-1.B.0` is an umbrella heading.** `hierarchy_role` is `umbrella`. It
   has no records and it is rated from its children. Never let it be accepted or
   rejected on its own.
4. **`DEMO-4.A.1` is a program requirement.** `addressability` is `program`. No
   curriculum can ever meet it. It is not a gap and must not read as one.
5. **One record is stale.** `review_status` is `stale`. Somebody already accepted
   it, and then the lesson changed underneath. This is the most important state
   on the screen. Make it obvious, and say that it was previously accepted.
6. **One record sits in a student-choice branch.** `is_choice_level` is true.
   Only some of the class does it. Show `choice_option` so the reviewer knows
   which branch, and never let the level be raised above introduced.
7. **One lesson has a blank unit number.** `displayed_number` is `""`. Print the
   unit's name. Never print `Unit ` with nothing after it.
8. **One lesson's number is the word `capstone`.** `lesson_token` is not always a
   number. If you sort by it, non-numeric tokens sort last.
9. **One lesson has no authored objective.** `has_objectives` is false. Say so.
   Do not invent one.
10. **One lesson's `lesson_key` is a former title.** It reads
    `guidelines-for-working`; the lesson is now called "Making Decisions with If
    and Else". **Never display `lesson_key`.** Display `lesson_name`. Use
    `stable_id` when you need to identify a lesson in code.
11. **The store can be empty.** Test it. Return `{"items": [], "total": 0}` from
    the loader and make sure the screen says something useful.

---

## 5. What the screen needs

**A header that shows progress.** Read `run.json` → `counts`. How many standards,
how many still to do, how many flagged, how many stale. Somebody working through
forty of these needs to see the end coming.

**One standard at a time**, with its statement, its boundary notes, and its
proposed evidence. The boundary notes are what the reviewer decides against, so
they cannot be hidden behind a click.

**Accept and Reject on each record.** Also let the reviewer change the level,
because the tool's proposed depth is often the thing that is wrong. A rejection
needs a reason — a rejection with no reason teaches nobody.

**A lock banner.** Check `standards-sets.json` for the set being reviewed. When
`publishable` is false, the results cannot go to a district, and the screen must
say so and keep the publish action switched off. Say why in plain words: the
boundary notes have not been checked by a person yet. This is a rule about
credibility, not a technical detail — do not let it be dismissed or hidden.

**A marker that says this is internal.** One already exists on the page. Keep it.
Nobody should mistake this screen for the public site.

**Decisions kept in the page for now.** There is no server yet. Hold the
reviewer's decisions in memory and add a button that downloads them as JSON. Do
not use `localStorage` as the real store — it is per-browser and it will be
thrown away when the API arrives.

---

## 6. Rules

These are not style preferences. Each one has already cost somebody time.

- **Every path is relative.** Write `../../contract/fixtures/`. Never write
  `/contract/fixtures/`. Every pull request is published to
  `pr-preview/pr-<number>/`, and a leading slash escapes that folder and loads
  the live site's file instead — so the preview shows the wrong thing rather than
  failing, and nobody notices.
- **No state or course names in your code.** The menus read what the store holds.
  If you type `Texas` or `AI Foundations` into a file, that is a bug.
- **No build step, no framework, no package to install.** Plain HTML, CSS and
  JavaScript. Somebody must be able to clone this and see it work with one
  command.
- **Do not edit `css/layout.css` or the root `index.html`.** Everyone touches
  those and you will collide. Your styles go in
  `tools/standards-mapper/style.css`, which is already linked.
- **Real controls.** `<button>`, `<a>`, `<details>`, `<label>` tied to inputs with
  `for`. Not a `<div>` with a click handler.
- **It must work by keyboard.** Every control reachable by Tab, operable by
  Enter or Space, with a visible focus outline. When the queue moves to the next
  standard, move focus with it and announce it in a live region. We build for
  school districts, and this is part of the work rather than a later pass.

---

## 7. You are done when

- [ ] All eleven cases in section 4 render correctly. Check them one by one.
- [ ] The counts in your header match the fixtures.
- [ ] The lock banner appears for the set whose `publishable` is false, and the
      publish action is off.
- [ ] You can get from the top of the page to the last control using only Tab,
      and operate every one of them.
- [ ] The browser console is clean.
- [ ] An empty store shows a sensible screen, not a blank one.
- [ ] `python3 contract/validate.py` still passes. If you changed a fixture, it
      will tell you what you broke.

Then push your branch and open a pull request. The preview link posted on it is
the easiest way for anybody to look at your work:

```
https://sammorris-code.github.io/codeai-sprint-scaffold/pr-preview/pr-<number>/tools/standards-mapper/
```

---

## 8. Two things to ask about, not decide

These are open on purpose. Build something reasonable, and flag which way you
went — do not settle them quietly.

1. **One card at a time, or a dense table with only the flagged rows opened?**
   Somebody working through forty standards may find cards slow. We do not know
   yet. If you build the cards and they feel slow to you, say so.
2. **Can a reviewer change the level, or only accept and reject?** The contract
   allows a change. Whether the screen should encourage it is a different
   question, and it affects how much the tool anchors the person.

---

## 9. Background, if you want it

You do not need these to start.

- `tools/standards-mapper/az-sprint-standards-pipeline-briefing.md` — why this
  work exists and what went wrong before.
- `contract/README.md` — the five rules governing the data.
- `contract/api.md` — every endpoint this screen will eventually call.
