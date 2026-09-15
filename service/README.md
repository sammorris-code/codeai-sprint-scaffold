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

1. **The password.** `standards:standards` is in `docker-compose.yml`. Move it
   to an environment variable the file does not contain.
2. **CORS.** `app/main.py` allows any origin. Narrow it to the interface's own
   address.
3. **Who is asking.** There is no authentication. Every reviewer decision
   records an `actor` string that nobody checks. `review_event` is ready for a
   real identity; nothing supplies one yet.
4. **Where it runs.** This is a laptop prototype. Moving it to a managed
   container is a hosting decision, not a code change.
5. **Backups.** None. The volume is the only copy.

None of these block building against it. All of them block a district seeing it.
