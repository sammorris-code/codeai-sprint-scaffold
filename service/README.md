# The store and its API

A prototype. Postgres holds the data; a small FastAPI service serves it.

**This is not the real store yet.** It runs on one machine, it has a password
written into a file, and it lets any web page call it. All three change before
it holds anything real. See *Before this holds real data* at the bottom.

---

## Run it

```bash
docker compose -f service/docker-compose.yml up
```

That brings up Postgres, applies the schema, loads the sample data, and starts
the API on <http://localhost:8000>.

Then:

- <http://localhost:8000/docs> — every endpoint, with a button to try each one
- <http://localhost:8000/api/standards-sets> — the registry
- <http://localhost:8000/api/runs/1/queue> — the review queue

Stop it with Ctrl and C. `docker compose ... down -v` also throws the data away.

### Your data survives a restart. It did not always.

The database lives in a named Docker volume (`pgdata`), so it survives `up`,
`down`, and a reboot. Only `down -v` destroys it.

That was never the risk. The risk was the `seed` service, which runs
`load_fixtures.py` on every `up` — and `load_fixtures.py` truncates all eleven
tables before loading the demo rows. A volume that persists perfectly, emptied
on every startup, persists nothing. **Anything you ingested would not have
survived your next `docker compose up`.**

So the seed step now looks first. If the database holds anything the fixtures
did not create — a standards set whose framework is not `DEMO`, or a curriculum
snapshot from a real commit — it prints what it found, loads nothing, and exits
0 so the API still starts.

```
The database holds work the fixtures did not put there:
  - standards set OK/CS-Standards/2018, 55 standards
  - curriculum snapshot bc34ca23dfee, 190 lessons

Leaving it alone. The sample data is not loaded.
```

`python3 service/load_fixtures.py --force` overwrites it anyway, when that is
what you want.

**`test_contract.py` resets the database before it runs**, for the same reason
and by the same route. It now refuses when the database holds real work, and
names what it would have destroyed. This is not hypothetical: a run of that
test against a working database deleted an ingested state framework, which is
why the guard exists. Point `DATABASE_URL` at a scratch database:

```bash
createdb standards_test          # or any empty database
DATABASE_URL=postgresql://localhost/standards_test python3 service/test_contract.py
```

`ALLOW_DESTRUCTIVE_RESET=1` overrides it, if you mean it.

---

## Point the interface at it

In `tools/standards-mapper/loader.js`, change the `SOURCE` block:

```js
mode: 'api',
base: 'http://localhost:8000/api',
```

That is the whole change. Nothing else in the page moves. The service was built
to return the same shapes as `contract/fixtures/`, and `test_contract.py` fails
if that stops being true.

---

## What is here

```
docker-compose.yml   Postgres, a one-shot loader, and the API
Dockerfile           the API image
requirements.txt     the Python packages
db/
  build_schema.py    builds schema.sql out of contract/tables.md
  schema.sql         GENERATED. Do not edit.
app/
  main.py            every endpoint
  db.py              the connection pool
  curriculum/        reads the upstream repository; see The curriculum corpus
    repo.py            blobs at one pinned commit, never a working tree
    levels.py          student-facing content, in both of its formats
    lessons.py         joins a unit file's tables into one record per lesson
    corpus.py          walks courses to units to lessons, writes the corpus
extract_curriculum.py  upstream  -> a corpus directory
load_curriculum.py     a corpus  -> a Postgres snapshot, and the stale pass
load_fixtures.py     puts contract/fixtures/ into Postgres
test_contract.py     proves the API returns what the fixtures promise
test_curriculum.py      extraction, against a synthetic upstream repo
test_curriculum_load.py loading and the stale pass, against Postgres
```

### The schema is generated, not written

`contract/tables.md` documents the eleven tables *and the reason for each one*,
in complete `CREATE TABLE` statements. Copying those into a separate SQL file by
hand would guarantee the two drift apart, and a schema that disagrees with its
own documentation is worse than none.

So the document is the source:

```bash
python3 service/db/build_schema.py          # rebuild schema.sql
python3 service/db/build_schema.py --check  # fail if it is stale
```

Change a table in `contract/tables.md`, with the reason, then re-run. CI fails
if the two disagree.

### The contract test is the point

```bash
python3 service/test_contract.py
```

190 checks. It asks the API for each thing and compares the answer to the
matching file in `contract/fixtures/`.

This is what makes the arrangement honest. The interface is built against the
fixtures while the store is still being written, then pointed here by changing
one block. That swap is only safe if the two agree, so something has to check —
and when they disagree, somebody has to decide which one is wrong.

---

## Ingesting a standards document

Three steps, and the first two need no API key.

**1. See what is in the document.** Writes nothing.

```bash
curl -X POST http://localhost:8000/api/standards-sets/characterize \
  -F "file=@service/sample_documents/DEMO_CS_2026.csv" \
  -F "claimed_count=14"
```

It reports the identifier scheme, the concepts, the extracted count against the
claimed count, which rows are headings rather than standards, every warning, and
**what drafting the boundaries will cost** — so the spend is approved before it
happens. Run it as often as you like; it is deterministic and free.

**2. Ingest it.** Needs `ANTHROPIC_API_KEY` — see *Where the key goes* below.

```bash
curl -X POST http://localhost:8000/api/standards-sets \
  -F "file=@service/sample_documents/DEMO_CS_2026.csv" \
  -F framework=DEMO -F standard_set=CS-DEMO -F set_type=standards \
  -F framework_year=2026 -F title="Demo Computer Science Standards"
```

**3. Check the boundaries — optional, and usually later.**
`GET /api/standards-sets/{id}/boundary-queue` returns every standard whose
boundary nobody has checked; a verdict on each records a decision, and when the
last one has a verdict `all_boundaries_checked` turns true.

Nothing waits on that. Publishing needs an approved run and nothing else, and a
boundary is normally checked when an alignment turns on it — with the lesson in
front of you — rather than in bulk up front. See `contract/REVIEW-DESIGN.md`.

### What is deterministic, and what is not

| Step | Needs a model? |
|---|---|
| Parse the document, extract statements word for word | No |
| Work out the identifier scheme and the hierarchy | No |
| Reconcile the count against the document's own claim | No |
| Draft the boundary statements | **Yes** |
| Write the set, run the review gate | No |

Only `app/ingestion/boundaries.py` calls Claude, and it is the only file that
does. Everything else about ingestion runs offline and free, which is why
`test_ingestion.py` can test all of it with the model call stubbed.

**Without a key the service still starts and characterization still works.**
Ingest returns a `503` explaining what is missing, and writes nothing — so the
document can simply be re-sent once a key is set. Boundaries are drafted before
anything is written, so a standard never exists in the store without one.

### Where the key goes

Two ways. Both keep the key out of git.

**A file.** Copy the example and edit it:

```bash
cp service/.env.example service/.env
# put your real key in service/.env
```

`service/.env` is git-ignored, as is any `.env` anywhere in this repository.
Verified: `git add -A` will not stage it. `service/.env.example` carries a
placeholder and is meant to be committed.

**Or your shell.** If you already export `ANTHROPIC_API_KEY` — for Claude Code,
say — Compose picks it up with no file at all:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
docker compose -f service/docker-compose.yml up
```

The shell wins over the file when both are set.

Either way it reaches only the `api` container. The database and the fixture
loader never see it, because neither has any use for it.

**Never put the key in `docker-compose.yml`.** That file is committed, and this
repository is public. A key pushed here is a key you have to revoke.

One caveat: Compose looks for `.env` beside the compose file it was given, so
the file belongs at `service/.env`, not the repository root. If the file route
does not work on your machine, export it in your shell instead — that path has
no ambiguity. I could not run Docker where this was built, so the file route is
reasoned from the Compose documentation rather than tested.

### The CSTA reference

`service/reference/` holds CSTA 2026: 196 foundational standards and 135
specialty ones. It is the anchor every other framework's boundaries are drafted
against, and the only source of identifiers `nearest_csta` may contain.

It is also what the analog gate checks against. Asking for an identifier gets an
assertion, and a first real run returned one for 80% of standards against a
prompt saying most have none. So the drafter now quotes the CSTA span it
adapted, and `ingestion/analogs.py` checks that quote is really in that standard
and really shows up in the boundary. Failures are dropped and counted, and the
count comes back in the ingest response under `nearest_csta.rejected` — a gate
set too strict would otherwise be indistinguishable from a drafter that stopped
stretching.

Only the standards whose grade band **overlaps** the document being ingested are
sent. Band labels do not agree between frameworks — CSTA says `9-12`, Oklahoma
says `9-10` and `11-12` — so they are compared by the grades they cover, not as
strings. Comparing them as strings would match nothing and the reference would
silently never be sent.

For a 9-12 state framework that is 46 of the 196, about 10k tokens, written to
the prompt cache once per run and read cheaply by every batch after the first.
It adds roughly 8 cents to a 55-standard run.

**An identifier the model returns that is not in the reference is dropped**, and
the run says how many. A fabricated identifier is worse than an empty list: it
looks like an audit trail and is not one.

Both files are labelled *(draft)* by their source, and this repository is
public. If that is the wrong home for them, move the folder and point `CSTA_DIR`
at it; nothing else changes.

### Cost

About **$0.44** for a 62-standard framework with Opus 5, halved on the Batch API.
`characterize` returns an estimate for the document in front of you. It is
derived from character counts, not a quote — measure exactly with
`count_tokens` once a key is set.

### Formats

CSV only so far. PDF and XLSX need a document-parsing step that is not built;
the API refuses them by name rather than half-reading them.

---

## The curriculum corpus

The standards half of the pipeline is above. This is the curriculum half: the
evidence an alignment claim is actually made against.

Two commands. The first reads upstream and writes a corpus; the second loads
that corpus into Postgres as a snapshot.

```bash
git clone --depth 1 --no-checkout -b staging \
  https://github.com/code-dot-org/code-dot-org.git cdo
python3 service/extract_curriculum.py --repo ./cdo --out ./out --courses aif
python3 service/load_curriculum.py --corpus ./out --make-current
```

`out/` and `cdo/` are git-ignored. **The upstream repository is read-only and
nothing here ever writes to it.**

### Clone it exactly like that

Both flags are load-bearing, and the briefing's recipe does not work on
Windows.

`--no-checkout`, because there is no working tree to check out into. 512 level
files have `:` or `?` in their names, which Windows forbids. `git checkout`
refuses those paths, abandons the whole `dashboard/config/levels/` directory —
all 64,258 files — and **exits 0**. An extractor reading the working tree then
reports success and finds no student instructions at all. Everything here is
read out of git object storage with `git cat-file`, which never touches the
filesystem and behaves the same on every machine.

No `--filter=blob:none`, because a partial clone fetches each blob on demand
and the demand here is a hundred thousand small files, one network round trip
each. Fetching them in one pack up front is the difference between seconds and
hours. It costs 280 MB, which is less than the sparse checkout it replaces.

### What comes out

```
manifest.csv          one row per lesson. Open this first.
manifest.json         the same, plus course and unit metadata and provenance
warnings.json         everything the run could not do cleanly
lessons/<unit>/NN-<slug>.md        readable lesson plan
lessons/<unit>/NN-<slug>.json      lesson-plan record
levels/<unit>/NN-<slug>.levels.md    student instructions, in student order
levels/<unit>/NN-<slug>.levels.json  student-instruction record
.cache/               the level-name index, keyed by commit. Safe to delete.
```

Both halves run in one command. They used to be two, and a corpus with lesson
plans but no student instructions is the exact undercount this pipeline exists
to prevent — a separate second step is a step that gets skipped.

### AIF today

```
3 courses, 15 distinct units, 190 lessons, 2,197 levels
129,080 student words, 6,065 instructional minutes
607 standard citations, all resolved to statement text
0 unresolved level references
```

Units are shared, so counts overlap on purpose: the full-year course reuses
both semesters' units, and each unit is extracted once and attributed to every
course that includes it. `--courses aid` adds AI Discoveries; extending to CSD
or CSP is a course key, not new code.

### Four ways to undercount without noticing

Each of these was found while building this, and each produced a corpus that
completed with no error and the wrong number in it.

**A third of the levels are not in the levels directory.** They are under
`dashboard/config/scripts/` as DSL text, and the file name is *sanitised*:
`ai_and_algorithmic_decisions_lesson10_..._2025.bubble_choice` on disk is
`ai-and-algorithmic-decisions-lesson10-...-2025` to the curriculum. You have to
open each file and read the `name` line inside. In one AIF unit that is 24 of
57 levels — 42%.

**Parent levels hold no text of their own.** `bubble_choice` and `level_group`
levels, and code levels with `contained_level_names`, keep their content in
their children. Expanding them multiplies the student word count 3.1x in a
sample unit. Reading parents only finds under a third of the words and reports
nothing.

**Some text is in a list, not a string.** A `Panels` level keeps everything a
student reads in `panels[].text`. A reader that only looks at string
properties records the level as empty. 37 AIF levels, several of them full
pages of explanation.

**Some levels are authored with curly quotes.** `question ‘Which of these…’`
instead of `'…'`. A parser that knows only `'` and `"` drops the question and
every answer option. 30 AIF levels.

The last two were worth 13,700 student words, 11% of the corpus. `warnings.json`
and the totals exist so the next one of these is visible rather than inferred.

### Change detection

Every lesson carries a `content_hash` over its content fields only — no
timestamps, no paths, no commit. The unit's own `serialized_at` cannot do this
job, because one edited section restamps the whole unit.

`load_curriculum.py` compares that hash against the `lesson_content_hash`
stored on every `alignment_record` — the hash as it was when the claim was
made. Every row that differs goes back to `stale` and returns to the review
queue, and every change is written to `review_event`. **This is the whole
answer to the stale-spreadsheet problem**, and it is why the store beats the
spreadsheet it replaces.

Loading does not promote a snapshot unless you pass `--make-current`, and it
never deletes the old one: a run is reproducible only while the lesson rows it
was made against still exist.

A snapshot need not cover every course, so "not in this snapshot" is not read
as "deleted upstream". The disappearance check is limited to units the snapshot
actually contains — otherwise the first AIF-only extraction would mark every
AID claim stale.

### Testing it

```bash
python3 service/test_curriculum.py        # no database, no network
python3 service/test_curriculum_load.py   # needs Postgres
```

The first builds a synthetic upstream repository containing one of each trap
above and asserts on what would otherwise be silent — including a level whose
file name cannot exist on Windows, written into the tree with `git
update-index` so it is in the commit but on no disk. The second makes a claim,
changes the lesson, loads a new snapshot, and checks that the right claim went
stale and the wrong ones did not.

---

## What the service enforces

These are not conventions. The service refuses, so no interface has to remember.

**The identity trio is required.** Ingesting a standards set without
`framework`, `standard_set` and `set_type` is a `422` naming the missing field.
The old schema turned a file that lost its identity into a CSTA 2026 file in
silence, so a wrong label could reach a district.

**The publish gate.** `/public` returns records only where the run is approved
*and* a person has checked the set's boundary notes. There is no parameter that
widens this. Approving a run whose notes are unchecked is a `409`.

**Both coverage percentages, always.** Against the whole framework and against
the part in scope, with `scope_note` beside them. Scope is a judgement; both
numbers are true and they differ. Returning one invites a reader to quote it
without its scope.

**Umbrella headings are excluded from totals.** They are rated by rollup from
their children. Counting them as well double-counts, which is how a coverage
percentage gets quietly inflated.

**A choice-level claim cannot be raised above introduced.** The evidence sits in
a branch only some students take.

**A rejection needs a reason.** A rejection with no reason teaches nobody.

**`all_boundaries_checked` is computed, never stored.** One rule, one place.
It reports whether every boundary in the set has been checked; it does not gate
publishing.

---

## Without Docker

Any Postgres 16 will do:

```bash
createdb standards
psql -d standards -f service/db/schema.sql
pip install -r service/requirements.txt
export DATABASE_URL="postgresql://localhost/standards"
python3 service/load_fixtures.py
python3 -m uvicorn service.app.main:app --reload
```

---

## Before this holds real data

1. **The database password.** `standards:standards` is in
   `docker-compose.yml`. Move it to an environment variable the file does not
   contain, the way `ANTHROPIC_API_KEY` already is.
2. **CORS.** `app/main.py` allows any origin. Narrow it to the interface's own
   address.
3. **Who is asking.** There is no authentication. Every reviewer decision
   records an `actor` string that nobody checks. `review_event` is ready for a
   real identity; nothing supplies one yet.
4. **Where it runs.** This is a laptop prototype. Moving it to a managed
   container is a hosting decision, not a code change.
5. **Backups.** None. The volume is the only copy.

None of these block building against it. All of them block a district seeing it.
