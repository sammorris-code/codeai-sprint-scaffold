-- GENERATED FILE. DO NOT EDIT.
--
-- Built from contract/tables.md by service/db/build_schema.py.
-- Change the tables there, with the reason for the change, then re-run:
--
--     python3 service/db/build_schema.py
--
-- CI fails if this file and that document disagree.

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

CREATE TABLE review_event (
  id          bigserial PRIMARY KEY,
  record_id   bigint REFERENCES alignment_record(id) ON DELETE CASCADE,
  standard_id bigint REFERENCES standard(id),
  actor       text NOT NULL,
  action      text NOT NULL,
  from_value  text,
  to_value    text,
  reason      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
