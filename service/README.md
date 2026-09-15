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
load_fixtures.py     puts contract/fixtures/ into Postgres
test_contract.py     proves the API returns what the fixtures promise
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

**3. Check the boundaries.** `GET /api/standards-sets/{id}/boundary-queue`, then
a verdict on each. When the last one has a verdict the set becomes publishable.
Nothing else can cause that.

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

**`publishable` is computed, never stored.** One rule, one place.

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
