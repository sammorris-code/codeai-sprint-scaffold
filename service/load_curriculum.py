#!/usr/bin/env python3
"""Load an extracted corpus into Postgres as a snapshot, and flag what went stale.

    python3 service/load_curriculum.py --corpus ./out
    python3 service/load_curriculum.py --corpus ./out --make-current

This is the second half of the curriculum pipeline. `extract_curriculum.py`
reads upstream and writes a corpus; this reads that corpus and writes the
`snapshot`, `course`, `unit`, `course_unit` and `lesson` tables.

**The stale pass is the point.** A mapping in a spreadsheet cannot tell you
which rows a curriculum update invalidated, so the alignment quietly goes out
of date and nobody knows which claims to re-check. Every `alignment_record`
stores `lesson_content_hash` — the hash of the lesson *as it was when the
claim was made*. Loading a new snapshot compares that against the hash the
lesson has now. Every row that differs goes back to `stale`, which returns it
to the review queue. Every change is written to `review_event`, because a gate
that cannot say who changed what and why is not a gate.

Two things this deliberately does not do.

It does not delete the old snapshot. Records point at the lesson rows they
were made against, and a run is reproducible only while those rows exist.
Snapshots are cheap; a claim nobody can trace is not.

It does not make the new snapshot current unless you ask. Extraction happens
on a schedule and review does not, so promoting a snapshot is a decision.
Pass `--make-current` to take it.
"""
import argparse
import json
import os
import pathlib
import sys

import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")

ACTOR = "system:load_curriculum"


def long_path(path):
    """Windows caps a path at 260 characters. See corpus.write()."""
    resolved = pathlib.Path(path).resolve()
    if os.name == "nt" and not str(resolved).startswith("\\\\?\\"):
        return pathlib.Path("\\\\?\\" + str(resolved))
    return resolved


def read_corpus(corpus_dir):
    """The manifest plus every lesson record it names."""
    root = long_path(corpus_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"No manifest.json in {corpus_dir}. "
                 f"Run service/extract_curriculum.py first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    lessons = []
    for unit_dir in sorted((root / "lessons").iterdir()):
        if not unit_dir.is_dir():
            continue
        for path in sorted(unit_dir.glob("*.json")):
            lessons.append(json.loads(path.read_text(encoding="utf-8")))
    return manifest, lessons


def load(conn, manifest, lessons, make_current, log=print):
    cur = conn.cursor()
    prov = manifest["provenance"]
    commit = prov["source_commit"]

    existing = cur.execute(
        "SELECT id FROM snapshot WHERE source_commit = %s", (commit,)).fetchone()
    if existing:
        sys.exit(f"Snapshot for commit {commit[:12]} is already loaded "
                 f"(id {existing['id']}). Nothing to do.\n"
                 f"Extract a newer commit, or drop that snapshot first.")

    totals = manifest.get("totals") or {}
    cur.execute("""INSERT INTO snapshot
        (source_repo, source_branch, source_commit, lesson_count, notes)
        VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (prov["source_repo"], prov["source_branch"], commit, len(lessons),
         f"{totals.get('units', 0)} units, "
         f"{totals.get('student_words', 0):,} student words, "
         f"extracted {prov['extracted_at']}"))
    snapshot_id = cur.fetchone()["id"]
    log(f"  snapshot {snapshot_id} for commit {commit[:12]}")

    # --- units, then courses, then the join ------------------------------
    # Units first, because a unit is shared between courses and must exist
    # once before either course can point at it.
    unit_ids = {}
    for unit in manifest["units"]:
        cur.execute("""INSERT INTO unit (snapshot_id, script_name, unit_name)
                       VALUES (%s, %s, %s) RETURNING id""",
                    (snapshot_id, unit["script_name"], unit["unit_name"]))
        unit_ids[unit["script_name"]] = cur.fetchone()["id"]
    log(f"  {len(unit_ids)} units")

    shared = 0
    for course in manifest["courses"]:
        cur.execute("""INSERT INTO course
                         (snapshot_id, course_key, course_name, semester)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (snapshot_id, course["course_key"], course["course_name"],
                     course.get("semester")))
        course_id = cur.fetchone()["id"]
        for unit in course["units"]:
            unit_id = unit_ids.get(unit["script_name"])
            if unit_id is None:
                # A course naming a unit the extraction did not produce is a
                # gap, not a detail. Say so rather than dropping it.
                log(f"    ! {course['course_key']} lists "
                    f"{unit['script_name']}, which is not in the corpus")
                continue
            cur.execute("""INSERT INTO course_unit
                           (course_id, unit_id, position, displayed_number)
                           VALUES (%s, %s, %s, %s)""",
                        (course_id, unit_id, unit["position"],
                         unit["displayed_number"]))
            shared += 1
    log(f"  {len(manifest['courses'])} courses, {shared} course-unit links")

    # --- lessons ---------------------------------------------------------
    for lesson in lessons:
        cur.execute("""INSERT INTO lesson
            (snapshot_id, unit_id, stable_id, lesson_key, lesson_name,
             lesson_token, lesson_group_key, lesson_group_name,
             lesson_group_position, relative_position, absolute_position,
             has_lesson_plan, has_objectives, content_hash, plan, levels)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (snapshot_id, unit_ids[lesson["script_name"]], lesson["stable_id"],
             lesson["lesson_key"], lesson["lesson_name"], lesson["lesson_token"],
             lesson.get("lesson_group_key"), lesson.get("lesson_group_name"),
             lesson.get("lesson_group_position"),
             lesson["relative_position"], lesson["absolute_position"],
             lesson["has_lesson_plan"], lesson["has_objectives"],
             lesson["content_hash"],
             json.dumps(lesson["plan"], ensure_ascii=False),
             json.dumps(lesson["levels"], ensure_ascii=False)))
    log(f"  {len(lessons)} lessons")

    stale = mark_stale(cur, snapshot_id, log)

    if make_current:
        # The partial unique index allows exactly one current snapshot, so the
        # old one has to step down in the same transaction.
        cur.execute("UPDATE snapshot SET is_current = false WHERE is_current")
        cur.execute("UPDATE snapshot SET is_current = true WHERE id = %s",
                    (snapshot_id,))
        log(f"  snapshot {snapshot_id} is now current")
    else:
        log("  not made current (pass --make-current to promote it)")

    conn.commit()
    return snapshot_id, stale


def mark_stale(cur, snapshot_id, log=print):
    """Return every claim whose lesson has changed to the review queue.

    Joins on `lesson_stable_id` rather than `lesson_id`, because the point is
    to compare a claim against a *different* snapshot's copy of the same
    lesson. `stable_id` is `script_name::lesson_key` and survives the swap;
    row ids do not.

    A lesson that has disappeared upstream is stale too. The claim may still
    be right, but nobody can check it any more, and that is the reviewer's
    call rather than this script's.

    **A snapshot need not cover every course.** Extraction is scoped — AIF
    today, AID later — so "this lesson is not in the new snapshot" usually
    means "this snapshot is not about that lesson", not "the lesson is gone".
    Treating the two the same would mark every AID claim stale the first time
    somebody extracted AIF alone, which is a large and very confusing wrong
    answer. The disappearance check is therefore limited to units the snapshot
    actually contains, matched on the `script_name` half of the stable id.
    """
    changed = cur.execute("""
        WITH current_hash AS (
            SELECT stable_id, content_hash
              FROM lesson WHERE snapshot_id = %(snap)s
        )
        UPDATE alignment_record r
           SET review_status = 'stale'
          FROM current_hash c
         WHERE c.stable_id = r.lesson_stable_id
           AND c.content_hash <> r.lesson_content_hash
           AND r.review_status <> 'stale'
        RETURNING r.id, r.lesson_stable_id, r.review_status,
                  r.lesson_content_hash, c.content_hash AS now_hash
    """, {"snap": snapshot_id}).fetchall()

    vanished = cur.execute("""
        UPDATE alignment_record r
           SET review_status = 'stale'
         WHERE r.review_status <> 'stale'
           AND split_part(r.lesson_stable_id, '::', 1) IN (
               SELECT script_name FROM unit WHERE snapshot_id = %(snap)s)
           AND NOT EXISTS (
               SELECT 1 FROM lesson l
                WHERE l.snapshot_id = %(snap)s
                  AND l.stable_id = r.lesson_stable_id)
        RETURNING r.id, r.lesson_stable_id
    """, {"snap": snapshot_id}).fetchall()

    for row in changed:
        cur.execute("""INSERT INTO review_event
            (record_id, actor, action, from_value, to_value, reason)
            VALUES (%s, %s, 'marked_stale', %s, 'stale', %s)""",
            (row["id"], ACTOR, row["lesson_content_hash"],
             f"Lesson {row['lesson_stable_id']} changed upstream: "
             f"{row['lesson_content_hash'][:12]} -> {row['now_hash'][:12]}"))
    for row in vanished:
        cur.execute("""INSERT INTO review_event
            (record_id, actor, action, from_value, to_value, reason)
            VALUES (%s, %s, 'marked_stale', NULL, 'stale', %s)""",
            (row["id"], ACTOR,
             f"Lesson {row['lesson_stable_id']} is not in this snapshot."))

    if changed or vanished:
        log(f"  {len(changed)} claims went stale because their lesson changed")
        if vanished:
            log(f"  {len(vanished)} claims point at a lesson that is gone")
    else:
        log("  no existing claims were affected")
    return len(changed) + len(vanished)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Load an extracted corpus into Postgres as a snapshot.")
    ap.add_argument("--corpus", required=True,
                    help="the directory extract_curriculum.py wrote")
    ap.add_argument("--make-current", action="store_true",
                    help="promote this snapshot to the current one")
    args = ap.parse_args(argv)

    manifest, lessons = read_corpus(args.corpus)
    print(f"Loading {len(lessons)} lessons from {args.corpus}")

    try:
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            snapshot_id, stale = load(conn, manifest, lessons,
                                      args.make_current)
    except psycopg.OperationalError as exc:
        sys.exit(f"Could not reach the database at {DSN}\n{exc}")

    print(f"\nSnapshot {snapshot_id} loaded. {stale} claims need re-checking.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
