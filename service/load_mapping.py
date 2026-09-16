#!/usr/bin/env python3
"""Load a hand-made mapping into the store as a run, so an interface has data.

    python3 service/load_mapping.py --csv mapping.csv --set 3 --actor "D. Reyes"

This exists to unblock the interface work. The review screen, the coverage
report and the public gate all read from `run`, `alignment_record` and
`standard_outcome`, and until something fills those tables there is nothing to
build against but fixtures.

**What comes in is a correlation list, not an alignment.** The file records
that a standard belongs on a lesson. It records no level, no evidence and no
reasoning, because nobody wrote them down. So this fills those columns with
placeholders and marks every record so that nothing downstream can mistake a
placeholder for a judgement:

  - `level` is set to `introduced`, the lowest value the column allows. It is
    not a claim that the lesson only introduces the standard; it is the value
    that understates rather than overstates while nobody knows.
  - `evidence` says in words that no evidence was recorded.
  - `flags` carries `imported_unverified`, so the review screen can show it and
    a query can find every one of them later.
  - `review_status` is `proposed`, which is what "needs your check" reads from.

**Nothing here may reach a district.** The records are unreviewed by
construction and the standards set's boundaries are drafted, so the publish
gate already refuses them twice over. Treat the run as scaffolding with a real
shape, and replace it when a judged run exists.

Lessons are resolved through `import_legacy.py`, which joins units by position
rather than displayed number and reports what will not resolve.
"""
import argparse
import collections
import csv
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from service.import_legacy import corpus_index, resolve, SEMESTER_COURSES  # noqa: E402

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")

PLACEHOLDER_EVIDENCE = (
    "No evidence recorded. This pairing comes from the {year} hand "
    "correlation, which listed the standard against the lesson and captured "
    "no task, level or reasoning. Read the lesson before accepting it.")

IMPORT_FLAG = {
    "kind": "imported_unverified",
    "label": "Imported, nobody judged this",
    "detail": "From a hand correlation with no level and no evidence. The "
              "level shown is a placeholder, not a finding.",
}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Load a hand mapping into the store as a run.")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--set", type=int, required=True, help="standards_set id")
    ap.add_argument("--actor", default="legacy import")
    ap.add_argument("--snapshot", type=int, default=None)
    ap.add_argument("--level", default="introduced",
                    choices=("introduced", "developed", "mastered"),
                    help="placeholder level for every imported record")
    ap.add_argument("--replace", action="store_true",
                    help="delete any previous import of this file first")
    args = ap.parse_args(argv)

    text = pathlib.Path(args.csv).read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))
    year = (rows[0].get("year") if rows else None) or "prior"

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        snapshot_id = args.snapshot or conn.execute(
            "SELECT id FROM snapshot WHERE is_current").fetchone()["id"]
        standards_set = conn.execute(
            "SELECT * FROM standards_set WHERE id = %s", (args.set,)).fetchone()
        if not standards_set:
            sys.exit(f"No standards set {args.set}.")

        standard_ids = {r["identifier"]: r["id"] for r in conn.execute(
            "SELECT id, identifier FROM standard WHERE set_id = %s",
            (args.set,)).fetchall()}

        by_token, by_taught, _ = corpus_index(conn, snapshot_id)

        # --- resolve every row -----------------------------------------
        per_course = collections.defaultdict(list)
        unresolved, unknown_standard = [], collections.Counter()
        for row in rows:
            identifier = (row.get("standard_id") or "").strip()
            if identifier not in standard_ids:
                unknown_standard[identifier] += 1
                continue
            lesson, why = resolve(row, by_token, by_taught)
            if lesson is None:
                unresolved.append((row, why))
                continue
            semester = (row.get("semester") or "").strip()
            course_key = SEMESTER_COURSES.get(semester)
            if not course_key:
                unresolved.append((row, "unknown semester"))
                continue
            per_course[course_key].append((lesson, identifier))

        print(f"Standards set : {standards_set['framework']}/"
              f"{standards_set['standard_set']}/"
              f"{standards_set['framework_year']}")
        print(f"Snapshot      : {snapshot_id}")
        print(f"Rows          : {len(rows)}")
        if unknown_standard:
            print(f"  {sum(unknown_standard.values())} rows name a standard "
                  f"the set does not hold: {', '.join(sorted(unknown_standard))}")
        if unresolved:
            grouped = collections.Counter(
                (r.get("semester"), r.get("unit"), r.get("lesson"), why)
                for r, why in unresolved)
            print(f"  {len(unresolved)} rows do not resolve to a lesson:")
            for (sem, unit, lesson_ref, why), n in grouped.most_common():
                print(f"    {n:>3}x  {sem} unit {unit} lesson {lesson_ref} — {why}")

        made = []
        for course_key, entries in sorted(per_course.items()):
            course = conn.execute("""
                SELECT id, course_name, semester FROM course
                 WHERE course_key = %s AND snapshot_id = %s""",
                (course_key, snapshot_id)).fetchone()
            if not course:
                print(f"  ! no course {course_key} in snapshot {snapshot_id}")
                continue

            if args.replace:
                conn.execute("""DELETE FROM run
                                 WHERE course_id = %s AND set_id = %s
                                   AND scope_note LIKE 'Imported hand%%'""",
                             (course["id"], args.set))

            scope = (f"Imported hand correlation, {year}. Every concept and "
                     f"grade band in the set. No level or evidence was "
                     f"recorded, so coverage here counts pairings, not "
                     f"judged alignment.")
            run_id = conn.execute("""
                INSERT INTO run (set_id, course_id, snapshot_id, scope_note,
                                 grain, status)
                VALUES (%s, %s, %s, %s, 'lesson', 'proposed') RETURNING id""",
                (args.set, course["id"], snapshot_id, scope)).fetchone()["id"]

            seen = set()
            written = 0
            for lesson, identifier in entries:
                key = (standard_ids[identifier], lesson["id"])
                if key in seen:
                    continue
                seen.add(key)
                conn.execute("""
                    INSERT INTO alignment_record
                      (run_id, standard_id, lesson_id, lesson_stable_id,
                       lesson_content_hash, level, evidence, note,
                       is_choice_level, flags, review_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,false,%s,'proposed')
                    ON CONFLICT (run_id, standard_id, lesson_id) DO NOTHING""",
                    (run_id, standard_ids[identifier], lesson["id"],
                     lesson["stable_id"], lesson["content_hash"], args.level,
                     PLACEHOLDER_EVIDENCE.format(year=year),
                     "imported from a hand correlation; level is a placeholder",
                     json.dumps([IMPORT_FLAG])))
                written += 1

            # One outcome per standard, misses included. That is what lets the
            # coverage screen answer "what percentage" at all.
            claimed = {identifier for _, identifier in entries}
            for identifier, standard_id in standard_ids.items():
                outcome = args.level if identifier in claimed else "not_addressed"
                conn.execute("""
                    INSERT INTO standard_outcome
                      (run_id, standard_id, outcome, in_scope, rationale)
                    VALUES (%s,%s,%s,true,%s)
                    ON CONFLICT (run_id, standard_id) DO NOTHING""",
                    (run_id, standard_id, outcome,
                     None if identifier in claimed else
                     "Not named anywhere in the imported correlation."))

            conn.execute("""
                INSERT INTO review_event (actor, action, to_value, reason)
                VALUES (%s, 'imported_mapping', %s, %s)""",
                (args.actor, str(run_id),
                 f"Loaded {written} pairings from {pathlib.Path(args.csv).name} "
                 f"for {course['course_name']}. No level or evidence in the "
                 f"source; placeholders written and flagged."))
            conn.commit()

            made.append((run_id, course, written, len(claimed)))
            print(f"\n  run {run_id}: {course['course_name']}"
                  f" ({course['semester'] or 'no semester'})")
            print(f"    {written} records, all proposed and flagged "
                  f"imported_unverified")
            print(f"    {len(claimed)} of {len(standard_ids)} standards claimed")

    print("\nEvery record needs checking and none can be published: the "
          "records are unreviewed and the set's boundaries are drafted, so "
          "the publish gate refuses them twice over.")
    print("Runs created: " + ", ".join(str(r) for r, *_ in made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
