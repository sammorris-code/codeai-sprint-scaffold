#!/usr/bin/env python3
"""Loads contract/fixtures/ into Postgres.

This is how the prototype gets something to serve. It is also a real check on
the contract: if a fixture does not fit the tables, this fails loudly here
rather than quietly later.

    python3 service/load_fixtures.py

Reads DATABASE_URL, or falls back to the Compose defaults.
"""
import json
import os
import pathlib
import sys

import psycopg

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contract" / "fixtures"
DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")


def fx(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def load(conn):
    cur = conn.cursor()

    # Wipe first so this is repeatable. Prototype only: the real store never
    # does this.
    cur.execute("""TRUNCATE review_event, standard_outcome, alignment_record, run,
                   lesson, course_unit, unit, course, snapshot, standard,
                   standards_set RESTART IDENTITY CASCADE""")

    # --- standards ------------------------------------------------------
    for s in fx("standards-sets")["items"]:
        cur.execute("""INSERT INTO standards_set
            (id, framework, standard_set, set_type, framework_year, title, source,
             scope, standard_count, boundary_provenance, schema_notes,
             reviewed_by, reviewed_on)
            VALUES (%(id)s, %(framework)s, %(standard_set)s, %(set_type)s,
                    %(framework_year)s, %(title)s, %(source)s, %(scope)s,
                    %(standard_count)s, %(boundary_provenance)s, %(schema_notes)s,
                    %(reviewed_by)s, %(reviewed_on)s)""", s)

    for s in fx("standards")["items"]:
        s = dict(s, extras=json.dumps(s.get("extras", {})))
        cur.execute("""INSERT INTO standard
            (id, set_id, identifier, statement, concept, subconcept, grade_band,
             level, boundary_includes, boundary_excludes, keywords,
             boundary_provenance, nearest_csta, hierarchy_role, rating_rule,
             addressability, parent_id, extras)
            VALUES (%(id)s, %(set_id)s, %(identifier)s, %(statement)s, %(concept)s,
                    %(subconcept)s, %(grade_band)s, %(level)s, %(boundary_includes)s,
                    %(boundary_excludes)s, %(keywords)s, %(boundary_provenance)s,
                    %(nearest_csta)s, %(hierarchy_role)s, %(rating_rule)s,
                    %(addressability)s, %(parent_id)s, %(extras)s)""", s)

    # --- curriculum -----------------------------------------------------
    for s in fx("snapshots")["items"]:
        cur.execute("""INSERT INTO snapshot
            (id, source_repo, source_branch, source_commit, extracted_at,
             is_current, lesson_count, notes)
            VALUES (%(id)s, %(source_repo)s, %(source_branch)s, %(source_commit)s,
                    %(extracted_at)s, %(is_current)s, %(lesson_count)s, %(notes)s)""", s)

    units_by_script = {}
    for c in fx("courses")["items"]:
        cur.execute("""INSERT INTO course (id, snapshot_id, course_key, course_name)
                       VALUES (%(id)s, %(snapshot_id)s, %(course_key)s, %(course_name)s)""", c)
        for u in c["units"]:
            cur.execute("""INSERT INTO unit (id, snapshot_id, script_name, unit_name)
                           VALUES (%s, %s, %s, %s)""",
                        (u["id"], c["snapshot_id"], u["script_name"], u["unit_name"]))
            cur.execute("""INSERT INTO course_unit
                           (course_id, unit_id, position, displayed_number)
                           VALUES (%s, %s, %s, %s)""",
                        (c["id"], u["id"], u["position"], u["displayed_number"]))
            units_by_script[u["script_name"]] = u["id"]

    for l in fx("lessons")["items"]:
        cur.execute("""INSERT INTO lesson
            (id, snapshot_id, unit_id, stable_id, lesson_key, lesson_name,
             lesson_token, relative_position, absolute_position, has_lesson_plan,
             has_objectives, content_hash, plan, levels)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (l["id"], 7, units_by_script[l["script_name"]], l["stable_id"],
             l["lesson_key"], l["lesson_name"], l["lesson_token"],
             l["relative_position"], l["absolute_position"], l["has_lesson_plan"],
             l["has_objectives"], l["content_hash"],
             json.dumps({"objectives": l.get("objectives", []),
                         "duration_minutes": l.get("duration_minutes")}),
             json.dumps([])))

    lesson_ids = {l["stable_id"]: l["id"] for l in fx("lessons")["items"]}

    # --- the run and its records ---------------------------------------
    r = fx("run")
    cur.execute("""INSERT INTO run
        (id, set_id, course_id, snapshot_id, scope_note, grain, status,
         previous_run_id, created_at, approved_by, approved_on)
        VALUES (%(id)s, %(set_id)s, %(course_id)s, %(snapshot_id)s, %(scope_note)s,
                %(grain)s, %(status)s, %(previous_run_id)s, %(created_at)s,
                %(approved_by)s, %(approved_on)s)""", r)

    records = outcomes = 0
    for item in fx("review-queue")["items"]:
        o = item["outcome"]
        cur.execute("""INSERT INTO standard_outcome
                       (run_id, standard_id, outcome, in_scope, rationale)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (r["id"], o["standard_id"], o["outcome"], o["in_scope"],
                     o.get("rationale")))
        outcomes += 1
        for rec in item["records"]:
            cur.execute("""INSERT INTO alignment_record
                (id, run_id, standard_id, lesson_id, lesson_stable_id,
                 lesson_content_hash, level, evidence, note, authorship,
                 is_choice_level, choice_option, flags, review_status,
                 reviewed_by, reviewed_on)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (rec["id"], r["id"], rec["standard_id"],
                 lesson_ids[rec["lesson"]["stable_id"]], rec["lesson"]["stable_id"],
                 rec["lesson_content_hash"], rec["level"], rec["evidence"],
                 rec.get("note"), rec.get("authorship"), rec["is_choice_level"],
                 rec.get("choice_option"), json.dumps(rec["flags"]),
                 rec["review_status"], rec.get("reviewed_by"), rec.get("reviewed_on")))
            records += 1

    # Keep the sequences ahead of the ids we forced in, or the first insert
    # through the API collides with a fixture row.
    for table in ("standards_set", "standard", "snapshot", "course", "unit",
                  "lesson", "run", "alignment_record"):
        cur.execute(f"""SELECT setval(pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table}), 1))""")

    conn.commit()
    return outcomes, records


if __name__ == "__main__":
    try:
        with psycopg.connect(DSN) as conn:
            outcomes, records = load(conn)
    except psycopg.OperationalError as e:
        sys.exit(f"Could not reach the database at {DSN}\n{e}")
    print(f"Loaded: {outcomes} standard outcomes, {records} alignment records.")
