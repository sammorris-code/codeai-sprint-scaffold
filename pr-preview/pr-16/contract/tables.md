# The store

Postgres. Eleven tables, not the six I estimated. The join table and the
separation of a run from a record account for the growth. Both are necessary,
and the reason is given below each one.

Nested curriculum content sits in `jsonb`. Identity and change-tracking fields
are promoted to real columns, so you query by identity and read the document
from the field. This is the reason to prefer Postgres over MySQL.

---

## 1. Standards

### `standards_set`

One row for each standards document. A state can publish more than one.

```sql
CREATE TABLE standards_set (
  id               bigserial PRIMARY KEY,
  framework        text NOT NULL,          -- the issuing body: DEMO, CSTA, NC, TX
  standard_set     text NOT NULL,          -- which document: CS-DEMO, CS10, CTE-ICT
  set_type         text NOT NULL           -- 'standards' | 'course_objectives'
                     CHECK (set_type IN ('standards','course_objectives')),
  framework_year   text NOT NULL,          -- '2026', '2025-26'. Text, not int.
  title            text NOT NULL,
  source           text,                   -- where the document came from
  scope            text,                   -- what part was ingested
  standard_count   integer NOT NULL,       -- as claimed. Reconciled on ingest.
  boundary_provenance text NOT NULL        -- the release gate
                     CHECK (boundary_provenance IN ('source','drafted','drafted+reviewed')),
  schema_notes     text,
  supersedes       bigint REFERENCES standards_set(id),
  superseded_by    bigint REFERENCES standards_set(id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  reviewed_by      text,
  reviewed_on      timestamptz,
  UNIQUE (framework, standard_set, framework_year)
);
```

**The identity trio is `framework`, `standard_set`, `set_type`. All three are
`NOT NULL`. There is no default.** This is the single correction the briefing
asks for. It is free now and expensive later.

`supersedes` and `superseded_by` answer the multi-vintage problem, which the
briefing lists as unsolved. The columns cost nothing empty. Adding them after
the store holds two vintages of one framework costs a migration.

`framework_year` is text. Vintages are written `2025-26`.

### `standard`

One row for each standard inside a set.

```sql
CREATE TABLE standard (
  id                  bigserial PRIMARY KEY,
  set_id              bigint NOT NULL REFERENCES standards_set(id) ON DELETE CASCADE,
  identifier          text NOT NULL,       -- the source's own id, verbatim
  statement           text NOT NULL,       -- verbatim. A paraphrase is a defect.
  concept             text NOT NULL,       -- drives scope filtering
  subconcept          text,
  grade_band          text,                -- grade_band or level. At least one.
  level               text,                -- 'S1','S2'. Never the course.
  boundary_includes   text[] NOT NULL,
  boundary_excludes   text[] NOT NULL DEFAULT '{}',
  keywords            text[] NOT NULL,
  boundary_provenance text NOT NULL
                        CHECK (boundary_provenance IN ('source','drafted','drafted+reviewed')),
  nearest_csta        text[] NOT NULL DEFAULT '{}',  -- drafting aid. Not a crosswalk.
  hierarchy_role      text NOT NULL DEFAULT 'standard'
                        CHECK (hierarchy_role IN ('umbrella','standard')),
  rating_rule         text NOT NULL DEFAULT 'direct'
                        CHECK (rating_rule IN ('direct','rollup')),
  addressability      text NOT NULL DEFAULT 'curriculum'
                        CHECK (addressability IN ('curriculum','program')),
  parent_id           bigint REFERENCES standard(id),
  extras              jsonb NOT NULL DEFAULT '{}',   -- practices, dispositions, examples
  UNIQUE (set_id, identifier)
);
```

`hierarchy_role` and `rating_rule` came from the California CTE run. An umbrella
row is rated by rollup from its children, never on its own. Without this, every
coverage percentage double-counts.

`addressability` marks a standard that no curriculum can meet, such as a program
or work-experience requirement. It gets its own reporting bucket. It is not a gap.

`nearest_csta` is a drafting aid and an audit trail. It is never a validated
crosswalk, and the interface must not present it as one.

---

## 2. Curriculum

The upstream repository is read-only. Nothing here ever writes to it. Each row
below is a derived copy.

### `snapshot`

One row for each extraction from upstream.

```sql
CREATE TABLE snapshot (
  id             bigserial PRIMARY KEY,
  source_repo    text NOT NULL,            -- 'code-dot-org/code-dot-org'
  source_branch  text NOT NULL,            -- 'staging'
  source_commit  text NOT NULL,            -- the commit extracted
  extracted_at   timestamptz NOT NULL DEFAULT now(),
  is_current     boolean NOT NULL DEFAULT false,
  lesson_count   integer NOT NULL,
  notes          text,
  UNIQUE (source_commit)
);
CREATE UNIQUE INDEX one_current_snapshot ON snapshot (is_current) WHERE is_current;
```

The snapshot replaces `curriculum_version`. It names the exact upstream commit,
so any claim can be traced to the curriculum it was made against.

### `course`, `unit`, `course_unit`

```sql
CREATE TABLE course (
  id           bigserial PRIMARY KEY,
  snapshot_id  bigint NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  course_key   text NOT NULL,              -- stable slug
  course_name  text NOT NULL,
  UNIQUE (snapshot_id, course_key)
);

CREATE TABLE unit (
  id           bigserial PRIMARY KEY,
  snapshot_id  bigint NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  script_name  text NOT NULL,              -- THE identifier. Stable and unique.
  unit_name    text NOT NULL,
  UNIQUE (snapshot_id, script_name)
);

CREATE TABLE course_unit (
  course_id      bigint NOT NULL REFERENCES course(id) ON DELETE CASCADE,
  unit_id        bigint NOT NULL REFERENCES unit(id) ON DELETE CASCADE,
  position       integer NOT NULL,         -- order within the course
  displayed_number text,                   -- what the screen shows. May be blank.
  PRIMARY KEY (course_id, unit_id)
);
```

**`course_unit` is a join table because units are shared between courses.** A
full-year course reuses the units of both semesters. Each unit is stored once and
attributed to every course that includes it. A foreign key from unit to course
would force a duplicate, and the duplicates would drift.

`displayed_number` is separate from `position`, and it is nullable, because the
two disagree in real courses. One observed course leaves the first four units
blank and numbers the last two 1 and 2. So `position` 2 and `displayed_number` 2
are different units. **Sort by `position`. Display `displayed_number`. Never
compute one from the other.**

### `lesson`

```sql
CREATE TABLE lesson (
  id              bigserial PRIMARY KEY,
  snapshot_id     bigint NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  unit_id         bigint NOT NULL REFERENCES unit(id) ON DELETE CASCADE,
  stable_id       text NOT NULL,           -- 'script_name::lesson_key'. JOIN ON THIS.
  lesson_key      text NOT NULL,           -- opaque. Goes stale on rename. Never display.
  lesson_name     text NOT NULL,           -- current title. Display this.
  lesson_token    text NOT NULL,           -- '4', 'capstone'. Bare. No 'L' prefix.
  relative_position  integer NOT NULL,
  absolute_position  integer NOT NULL,
  has_lesson_plan boolean NOT NULL DEFAULT true,
  has_objectives  boolean NOT NULL DEFAULT true,
  content_hash    text NOT NULL,           -- content fields only. No timestamps.
  plan            jsonb NOT NULL DEFAULT '{}',   -- the lesson plan record
  levels          jsonb NOT NULL DEFAULT '[]',   -- student instructions, in student order
  UNIQUE (snapshot_id, stable_id)
);
CREATE INDEX lesson_hash ON lesson (content_hash);
CREATE INDEX lesson_plan_gin ON lesson USING gin (plan);
```

`plan` and `levels` hold the nested extraction as `jsonb`. They nest four deep:
activity, section, level, sublevel. Flattening them into tables would lose the
order a student meets them in, and nothing queries below the lesson.

`content_hash` fingerprints the content fields only. Provenance and timestamps
are excluded, so the hash changes when the content changes and not otherwise.
**Do not use the unit timestamp for this.** One edited section restamps a whole
unit, so it cannot say which lesson changed.

`has_objectives` is false for a project lesson with no authored objective. There
is nothing to anchor a forward claim on. The interface must say so rather than
infer one.

---

## 3. Alignment

### `run`

One row for each alignment run. A run is one standards set against one course.

```sql
CREATE TABLE run (
  id            bigserial PRIMARY KEY,
  set_id        bigint NOT NULL REFERENCES standards_set(id),
  course_id     bigint NOT NULL REFERENCES course(id),
  snapshot_id   bigint NOT NULL REFERENCES snapshot(id),
  scope_note    text NOT NULL,             -- which concepts. Never publish a % without it.
  grain         text NOT NULL DEFAULT 'lesson' CHECK (grain IN ('lesson','unit')),
  status        text NOT NULL DEFAULT 'proposed'
                  CHECK (status IN ('proposed','in_review','approved','superseded')),
  previous_run_id bigint REFERENCES run(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  approved_by   text,
  approved_on   timestamptz
);
```

`scope_note` is a required column on purpose. Coverage against a whole framework
and coverage against the part in scope are both true and they differ by half.
**A percentage without its scope beside it is a wrong number.**

`previous_run_id` gives "compare to last run" a place to read from.

### `alignment_record`

One row for each (standard, lesson) pair. A standard evidenced in three lessons
gets three rows.

```sql
CREATE TABLE alignment_record (
  id              bigserial PRIMARY KEY,
  run_id          bigint NOT NULL REFERENCES run(id) ON DELETE CASCADE,
  standard_id     bigint NOT NULL REFERENCES standard(id),
  lesson_id       bigint NOT NULL REFERENCES lesson(id),
  lesson_stable_id text NOT NULL,          -- denormalized, survives a snapshot swap
  lesson_content_hash text NOT NULL,       -- the hash AT THE TIME OF THE CLAIM
  level           text NOT NULL            -- this lesson's contribution
                    CHECK (level IN ('introduced','developed','mastered')),
  evidence        text NOT NULL,           -- the specific task. Not the topic.
  note            text,                    -- caveats, caps, 'added on reconciliation'
  authorship      text                     -- who wrote the code
                    CHECK (authorship IN ('student_authored',
                                          'student_directed_ai_produced_student_verified',
                                          'ai_produced_not_verified')),
  is_choice_level boolean NOT NULL DEFAULT false,
  choice_option   text,                    -- which branch, when is_choice_level
  flags           jsonb NOT NULL DEFAULT '[]',
  review_status   text NOT NULL DEFAULT 'proposed'
                    CHECK (review_status IN ('proposed','accepted','rejected','changed','stale')),
  reviewed_by     text,
  reviewed_on     timestamptz,
  UNIQUE (run_id, standard_id, lesson_id)
);
CREATE INDEX record_queue ON alignment_record (run_id, review_status);
```

**`lesson_content_hash` is the field that matters.** It stores the hash as it was
when the claim was made. Re-extract upstream, compare against the lesson's current
hash, and every row that differs is a row to re-check. Its `review_status` becomes
`stale` and it returns to the queue. This is the whole answer to the stale
spreadsheet problem, and it works the same in Postgres as it did in git.

`level` here holds three values, not four. A record is a claim that a lesson
contributes. There is no record for a standard the course misses. `not_addressed`
lives on the outcome, below.

`authorship` records who wrote the code. It does not judge. The judgement is one
written decision for each framework, made once, rather than an implicit judgement
made on every lesson.

`flags` is an array of objects. The interface reads `kind` and shows the label:

```json
[{"kind":"depth_doubt","label":"Lesson may not go deep enough","detail":"..."},
 {"kind":"weak_match","label":"Close match, likely not a real one","detail":"..."},
 {"kind":"overclaim","label":"This lesson carries many standards","detail":"..."},
 {"kind":"artifact_mismatch","label":"The standard asks for a different artifact","detail":"..."}]
```

### `standard_outcome`

One row for each standard in a run, including the misses.

```sql
CREATE TABLE standard_outcome (
  run_id       bigint NOT NULL REFERENCES run(id) ON DELETE CASCADE,
  standard_id  bigint NOT NULL REFERENCES standard(id),
  outcome      text NOT NULL
                 CHECK (outcome IN ('mastered','developed','introduced',
                                    'not_addressed','boundary_issue',
                                    'not_curriculum_addressable')),
  in_scope     boolean NOT NULL DEFAULT true,
  rationale    text,
  PRIMARY KEY (run_id, standard_id)
);
```

**This table is why the store beats the spreadsheet.** A mapping holds matches
only, so it cannot answer "what percentage do you cover", which is the question
states ask. This table holds one row for every standard, misses included.

The six values are exclusive and they sum to the candidate set. The count check
is a query, not a spreadsheet formula.

**One deliberate change from the CSV.** The old CSV repeated the aggregate rating
on every contributing row. The aggregate lives here once instead. The CSV export
rebuilds that column by joining. Nothing is lost and the two can no longer
disagree.

### `review_event`

```sql
CREATE TABLE review_event (
  id          bigserial PRIMARY KEY,
  record_id   bigint REFERENCES alignment_record(id) ON DELETE CASCADE,
  standard_id bigint REFERENCES standard(id) ON DELETE CASCADE,
  actor       text NOT NULL,
  action      text NOT NULL,
  from_value  text,
  to_value    text,
  reason      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
```

The boundary gate is a claim about who checked what. A claim needs a record.
This table is also what a state asks for when it questions a number.

**Both foreign keys cascade.** They did not agree at first: `record_id` cascaded
and `standard_id` did not, which made deleting a mis-ingested standards set
impossible — a thing you do constantly while a prototype is being built. They now
behave the same.

Cascading is the right default here because an audit event about a standard that
no longer exists cannot be interpreted by anybody, including the state asking the
question. The audit value is in events about live data.

**If a permanent, deletion-proof audit trail is needed later, do not make these
foreign keys orphan their events.** Forbid deleting a standards set instead, and
supersede it — which is the same answer the multi-vintage problem needs, and
should be solved once for both.

---

## The publish gate, as a query

The public site never filters. The API refuses to serve an ungated record.

```sql
SELECT o.* FROM standard_outcome o
  JOIN run r          ON r.id = o.run_id
  JOIN standards_set s ON s.id = r.set_id
 WHERE r.status = 'approved'
   AND s.boundary_provenance = 'drafted+reviewed';
```

Two conditions, both required. The run is approved, and the set's boundaries were
checked by a person. Anything else is internal.
