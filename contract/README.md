# The contract

This folder defines the shape of the Standards data. It is the agreement between
three pieces of work that run at the same time:

| Work | Who | Reads this folder for |
|---|---|---|
| The interface (#3a review tool, #3b public site) | UI | field names, payloads, fixtures |
| The store (Postgres) and the API (FastAPI) | Store | table shapes, endpoints |
| The engine (ingestion, alignment) | Engine | what it must emit |

Nobody waits for anybody. All three read this folder and meet at the end.

**This folder holds no real data.** Every fixture is invented. See *Fixtures*.

---

## Read this first

The briefing at `tools/standards-mapper/az-sprint-standards-pipeline-briefing.md`
holds the reasoning. This folder holds the decisions that came out of it.

Five rules control everything here.

1. **The identity trio is required.** Every standards set carries `framework`,
   `standard_set`, and `set_type`. There is no default. A file without all three
   is rejected. The old schema defaulted a missing trio to CSTA 2026, so a file
   that lost its identity became a CSTA file in silence. That is fixed here.
2. **No state is built in.** The interface reads the list of sets from the API.
   It never holds a list of states in its own code.
3. **Boundary review is a release gate.** A set carries `boundary_provenance`.
   The public site shows records from a set marked `drafted+reviewed` only.
4. **Identity is `stable_id` and `script_name`.** Never a unit number. Never a
   lesson title. Unit numbers repeat and lesson keys do not follow renames.
5. **`content_hash` detects change.** When a lesson changes, every alignment
   record that points at it goes stale and returns to the review queue.

---

## The files

```
README.md          this file
tables.md          the store. Table shapes, with the reason for each.
api.md             the API. Endpoints and payloads.
schema/*.json      JSON Schema for each object. Machine readable.
fixtures/*.json    invented data with the real shape. For the interface.
validate.py        checks every fixture against its schema.
```

---

## Fixtures

A fixture is invented data with a real shape. It uses the correct field names
and the correct structure. The content is fake.

The interface reads fixtures today and reads the API later. It cannot tell the
difference, because the shape is the same.

**The fixtures are also a test set.** Each one carries a case that breaks a naive
interface. Handle all of them and the real data holds no surprise:

| Fixture case | What it tests |
|---|---|
| A set marked `drafted` | The publish lock. The public site must refuse it. |
| A unit with a blank number | The interface must not print `Unit `. |
| A lesson named `capstone` | Lesson tokens are not always numbers. They sort last. |
| A record capped at `introduced` on a choice level | The cap and its reason must show. |
| A standard with no evidence | `not_addressed` must render, not vanish. |
| A standard marked `boundary_issue` | This is a fifth bucket, not a failure. |
| An umbrella standard | Rated by rollup. Never counted on its own. |
| A standard marked `program` addressability | No curriculum can meet it. Sixth bucket. |
| A record marked `stale` | The lesson changed under a confirmed match. |
| A lesson with no authored objective | Nothing to anchor a claim on. |
| An empty set list | The first day. The store is empty. |

**Two rules, because this repository is public.**

- Every invented framework is named `DEMO`. Never name a real state.
- Never copy a real district name, a real standard statement, or a real coverage
  number. A screenshot of a demo must never read as a claim.

---

## Validate

```bash
python3 contract/validate.py
```

It checks every fixture against its schema. It needs no install. Run it before
you commit a change to this folder.
