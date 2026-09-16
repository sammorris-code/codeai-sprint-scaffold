# The API

FastAPI over Postgres. Two surfaces on one service.

| Surface | Prefix | Audience | Serves |
|---|---|---|---|
| Internal (#3a) | `/api` | Staff. Contractors, curriculum team, RPs. | everything, drafts included |
| Public (#3b) | `/public` | Districts. Anonymous. | approved records only |

**The split is enforced in the service, not in the interface.** A `/public`
endpoint cannot return an unapproved record, whatever it is asked for. An
interface bug must not be able to leak a draft.

Every payload below has a fixture in `fixtures/`. Build against the fixture.

---

## Conventions

- JSON in, JSON out. `Content-Type: application/json`.
- A list endpoint returns `{"items": [...], "total": n}`.
- An error returns `{"error": {"code": "...", "message": "...", "field": "..."}}`.
- Times are RFC 3339 in UTC.
- Identifiers in a URL are the numeric `id`. `stable_id` is a query filter.

---

## Standards sets

### `GET /api/standards-sets`
The registry. **This replaces the hardcoded framework list on the page.**

Query: `framework`, `set_type`, `provenance`, `q`.

Fixture: `standards-sets.json`, and `standards-sets-empty.json` for day one.

```json
{"items": [{
  "id": 1,
  "framework": "DEMO",
  "standard_set": "CS-DEMO",
  "set_type": "standards",
  "framework_year": "2026",
  "title": "Demo Computer Science Standards",
  "standard_count": 12,
  "boundary_provenance": "drafted",
  "all_boundaries_checked": false,
  "reviewed_by": null,
  "reviewed_on": null,
  "created_at": "2026-09-15T10:00:00Z"
}], "total": 1}
```

`all_boundaries_checked` is computed: true when `boundary_provenance` is
`drafted+reviewed`.
The interface reads this one field. It never re-derives the rule.

**It no longer gates publishing**, despite the name. Publishing needs an approved
run and nothing else — `REVIEW-DESIGN.md` says why the set-level condition went.
What the field still tells you truthfully is whether every boundary in the set
has been checked by a person, which is worth showing. The name is now a poor
description of what it reports and is a candidate to be renamed; it is kept for
the moment because three screens read it.

### `POST /api/standards-sets/characterize`
Read a document and report what is in it. **Writes nothing.**

Multipart: `file` (CSV), optional `claimed_count`.

This is the step the briefing puts before everything else — report the
characterization, agree the scope, then continue. It is deterministic and free,
so it can be run as often as somebody likes while working out whether a document
is what they think it is.

Returns the identifier scheme, the concepts, the extracted count against the
claimed count, how many rows are headings rather than standards, how many carry
the source's own clarifying text, every warning, and **an estimate of what
drafting the boundaries will cost** — so a spend is approved before it happens.

Fixture: `ingest-characterization.json`.

### `POST /api/standards-sets`
Ingest the document: draft the boundaries and write the set.

Multipart: `file`, plus `framework`, `standard_set`, `set_type`,
`framework_year`, `title`, and optionally `source`, `scope`, `claimed_count`.

**The identity trio is required.** Omit any of the three and the API returns
`422` naming the one that is missing. It does not guess, and it does not default
to CSTA.

**Boundaries are drafted before anything is written**, so a standard never exists
in the store without one. If drafting fails — no API key, a model error — nothing
is written at all, and the document can simply be re-sent once the problem is
fixed. A half-written set is harder to reason about than no set.

The new set is always `drafted`, and that no longer blocks anything. Its results
can be published as soon as a run against it is approved. Its boundaries get
checked when an alignment makes one matter, not before.

### `GET /api/standards-sets/{id}/boundary-queue`
No longer a gate — nothing waits on it. It is a worklist for anyone who wants to
check boundaries ahead of time, and the place a boundary raised by an alignment
is answered. Returns every standard whose boundary nobody has
checked yet, with the drafted text.

A drafted boundary means a later rejection may be the boundary's fault rather
than the curriculum's. Say so on screen.

Fixture: `boundary-queue.json`.

### `POST /api/standards/{id}/boundary-verdict`
```json
{"verdict": "accept", "edited_includes": null, "edited_excludes": null,
 "actor": "sam.morris@code.org", "reason": null}
```

`verdict` is `accept` or `edit`; an `edit` carrying no edits is a `422`. When
every standard in the set has a verdict, **the set flips to `drafted+reviewed`
and `all_boundaries_checked` becomes true.** Only this endpoint can cause that
flip.

That flip used to be what let results reach a district. It is not any more —
publishing needs an approved run and nothing else. See `REVIEW-DESIGN.md`.

Every verdict is written to `review_event` with the actor.

### `GET /api/standards-sets/{id}/standards`
Fixture: `standards.json`.

---

## Curriculum

The upstream repository is read-only. These endpoints read a snapshot. **No
endpoint writes upstream. None will.**

### `GET /api/snapshots`
Fixture: `snapshots.json`.

### `POST /api/snapshots/refresh`
Starts an extraction from upstream. Returns a job id. This is a scheduled job,
not a monitor.

### `GET /api/courses?snapshot_id=`
Fixture: `courses.json`. Note the unit whose `displayed_number` is empty.

### `GET /api/lessons?course_id=`
Fixture: `lessons.json`. Note the capstone, whose `lesson_token` is not a number.

Ordered by the unit's position in the course, then the lesson's own position.
`absolute_position` is absolute *within a unit*, so ordering by it alone
interleaves the units. A unit belongs to more than one course, so each lesson
is returned once whether or not a course is named.

### `GET /api/lessons/{id}`
One lesson, whole: the same identity fields plus `plan` and `levels`. The list
above returns a summary because a course is 190 lessons and the nested records
are large. Read by `tools/corpus-browser/`.

---

## Runs and review

### `POST /api/runs`
```json
{"set_id": 1, "course_id": 1, "grain": "lesson",
 "scope_note": "All concepts, grades 9-12",
 "concepts": null}
```
`scope_note` is required. A run without a stated scope produces a percentage
nobody can defend.

### `GET /api/runs/{id}`
Fixture: `run.json`. Holds the counts for the queue header.

### `GET /api/runs/{id}/queue`
**The main screen.** One standard at a time, with its records and evidence.

Query: `status` (`proposed` default), `flagged` (bool), `concept`, `cursor`.

Fixture: `review-queue.json`. It carries every case listed in the README.

```json
{"items": [{
  "standard": {"id": 101, "identifier": "DEMO-1.A.1", "statement": "...",
               "concept": "Algorithms", "hierarchy_role": "standard",
               "rating_rule": "direct", "addressability": "curriculum",
               "boundary_includes": ["..."], "boundary_excludes": ["..."],
               "boundary_provenance": "drafted"},
  "outcome": {"outcome": "developed", "in_scope": true, "rationale": null},
  "records": [{
     "id": 5001,
     "lesson": {"stable_id": "demo-unit-one-2026::lesson-3",
                "lesson_name": "Sorting a List by Hand",
                "lesson_token": "3", "unit_name": "Demo Unit One",
                "displayed_number": "1", "position": 1,
                "has_objectives": true},
     "level": "developed",
     "evidence": "Students order ten cards and write the rule they used.",
     "note": null,
     "authorship": "student_authored",
     "is_choice_level": false, "choice_option": null,
     "flags": [],
     "review_status": "proposed",
     "lesson_content_hash": "h3a1..."}],
  "counts": {"records": 1, "flagged": 0}
}], "total": 12, "cursor": null}
```

### `PATCH /api/records/{id}`
One reviewer decision.

```json
{"review_status": "accepted", "level": null,
 "actor": "sam.morris@code.org", "reason": null}
```

`level` answers the briefing's open question 6. Send `null` to accept as
proposed. Send a level to accept at a different depth. **The reviewer can change
the level.** The API records both the old and the new value in `review_event`, so
the change is visible later.

Rejecting requires a `reason`. A rejection with no reason teaches nobody.

### `GET /api/runs/{id}/coverage`
One row for every standard, misses included. Fixture: `coverage.json`.

```json
{"run_id": 1,
 "scope_note": "All concepts, grades 9-12",
 "in_scope": {"total": 12, "covered": 7, "percent": 58},
 "whole_framework": {"total": 14, "covered": 7, "percent": 50},
 "buckets": {"mastered": 2, "developed": 3, "introduced": 2,
             "not_addressed": 3, "boundary_issue": 1,
             "not_curriculum_addressable": 1},
 "count_check": {"sum": 12, "candidate_set": 12, "ok": true},
 "covered_with_caveat": 3,
 "rows": [ ... ]}
```

**Both percentages are returned, always.** Scope is a judgement. Returning one
number invites a reader to quote it without its scope. `covered_with_caveat`
counts rows covered in part, so you know which number you are quoting before a
state asks.

`count_check` is the seventh verification check, computed server-side. The
interface shows a warning when `ok` is false rather than printing a total it
cannot justify.

### `GET /api/runs/{id}/diff?against={run_id}`
Compare to last run. Fixture: `run-diff.json`.

```json
{"stale": [{"record_id": 5003, "lesson_stable_id": "...",
            "was_hash": "h9c2...", "now_hash": "h9c7...",
            "lesson_name": "Making Decisions with If and Else",
            "previous_status": "accepted"}],
 "added": [], "removed": [], "level_changed": []}
```

`stale` is produced by comparing `lesson_content_hash` on the record against the
lesson's current hash. Those records return to the queue. Nobody watches a
directory. A scheduled job re-extracts and this endpoint reports the result.

### `POST /api/runs/{id}/approve`
Sets `run.status` to `approved`. **This is the release gate, enforced by the
service, and approval is the whole of it.**

It used to refuse with `409` when the set was not `drafted+reviewed`. That
condition is gone — see `REVIEW-DESIGN.md` — and nothing about the set's
boundary notes is consulted here any more.

The one refusal left is arithmetic, not judgement: `409 count_mismatch` when the
coverage buckets do not sum to the candidate set, which means a standard has no
outcome row. A total nobody can justify must not be approved.

---

## Public

Every endpoint returns approved records from reviewed sets only. There is no
parameter that widens this.

### `GET /public/standards-sets`
Only sets with at least one approved run.

### `GET /public/coverage?set_id=&course_id=`
The district view. Fixture: `public-coverage.json`.

Returns the same shape as the internal coverage, minus `rationale`, minus flags,
minus reviewer names.

**It includes `not_addressed` rows.** Whether to show them is a live decision
(briefing open question 3). The API returns them and the interface decides. Put
the switch in one place, and make it a setting somebody chose, not an accident of
what the endpoint happened to send.

### `GET /public/standards/{id}/courses`
The reverse question: which courses teach this standard?

### `GET /public/coverage.pdf?set_id=&course_id=`
The board packet. Server-rendered, so a district gets the same page an RP linked.

---

## Errors

| Code | When |
|---|---|
| `422 identity_trio_missing` | An ingest request omits `framework`, `standard_set`, or `set_type` |
| `409 set_not_reviewed` | Approving a run whose set is not `drafted+reviewed` |
| `409 count_mismatch` | The six buckets do not sum to the candidate set |
| `404 not_published` | A `/public` request for a record that is not approved |
| `422 scope_note_required` | Creating a run with no stated scope |
| `409 count_mismatch` (ingest) | The document's claimed count and the extracted count differ |
| `409 already_ingested` | That framework, set and year is already in the store |
| `422 unsupported_format` | The document is not a CSV; PDF and XLSX are not built yet |
| `422 cannot_read_document` | No column looks like the identifier or the statement |
| `503 boundary_drafting_unavailable` | No API key, so boundaries cannot be drafted. Nothing was written |
| `502 boundary_drafting_failed` | Drafting failed. Nothing was written; re-send the document |

The first one is the correction this contract exists to make. It is an error, not
a default.
