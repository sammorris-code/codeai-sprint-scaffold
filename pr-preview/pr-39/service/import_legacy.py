#!/usr/bin/env python3
"""Load a hand-made mapping CSV and check it against the corpus.

    python3 service/import_legacy.py --csv path/to/mapping.csv --course AIF

A legacy mapping names a lesson by course, semester, unit number and lesson
number. None of those three are durable: units are renumbered, lessons are
renamed, and a lesson's number shifts when an assessment shell is added above
it. So the first job is to resolve each row to a `stable_id` and say plainly
which rows will not resolve.

This is the deterministic half of reconciliation and it needs no model. It
answers three questions before any engine runs:

  - Does every standard id in the file exist in the standards set?
  - Does every (semester, unit, lesson) triple name a lesson that exists?
  - What does the file actually claim, once resolved?

**Unit numbers are resolved by position, not by displayed number.** The two
disagree in AIF Semester 2, where the first four units show no number and the
last two show 1 and 2. A legacy file that numbers S2 units 1 to 6 in teaching
order is using position, so that is what this joins on — and it says so, rather
than guessing silently.
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

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")

# Which course each semester label means. A legacy file says "S1"; the corpus
# knows course keys.
SEMESTER_COURSES = {
    "S1": "ai-foundations-exploring-ai-and-cs-2026",
    "S2": "ai-foundations-designing-and-building-with-ai-2026",
}


def corpus_index(conn, snapshot_id):
    """(course_key, unit position, lesson token) -> lesson row.

    Also indexes by the lesson's ordinal among lessons that have a plan,
    because a legacy file usually counts teaching lessons and ignores the
    assessment shells sitting between them.
    """
    rows = conn.execute("""
        SELECT l.id, l.stable_id, l.lesson_name, l.lesson_token,
               l.content_hash, l.has_lesson_plan, l.relative_position,
               l.lesson_group_name,
               u.script_name, c.course_key, cu.position AS unit_position,
               cu.displayed_number
          FROM lesson l
          JOIN unit u ON u.id = l.unit_id
          JOIN course_unit cu ON cu.unit_id = u.id
          JOIN course c ON c.id = cu.course_id
         WHERE l.snapshot_id = %(snap)s AND c.snapshot_id = %(snap)s
         ORDER BY c.course_key, cu.position, l.absolute_position
    """, {"snap": snapshot_id}).fetchall()

    by_token = {}
    by_taught_ordinal = {}
    taught_counter = collections.Counter()
    for row in rows:
        key = (row["course_key"], row["unit_position"])
        by_token[(key, str(row["lesson_token"]))] = row
        if row["has_lesson_plan"]:
            taught_counter[key] += 1
            by_taught_ordinal[(key, taught_counter[key])] = row
    return by_token, by_taught_ordinal, rows


def resolve(row, by_token, by_taught_ordinal):
    """One legacy row to a lesson, with how it was matched."""
    course_key = SEMESTER_COURSES.get((row.get("semester") or "").strip())
    if not course_key:
        return None, "unknown semester"
    try:
        unit_position = int((row.get("unit") or "").strip())
    except ValueError:
        return None, "unit is not a number"
    token = (row.get("lesson") or "").strip()
    key = (course_key, unit_position)

    hit = by_token.get((key, token))
    if hit:
        return hit, "lesson token"

    # A legacy file usually counts only the lessons that are taught.
    try:
        ordinal = int(token)
    except ValueError:
        return None, "lesson is not a number and no token matched"
    hit = by_taught_ordinal.get((key, ordinal))
    if hit:
        return hit, "position among taught lessons"
    return None, f"no lesson {token} in unit at position {unit_position}"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Check a hand-made mapping against the corpus.")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--snapshot", type=int, default=None,
                    help="default: the current snapshot")
    ap.add_argument("--out", default=None,
                    help="write the resolved rows here as JSON")
    args = ap.parse_args(argv)

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        snapshot_id = args.snapshot
        if snapshot_id is None:
            current = conn.execute(
                "SELECT id FROM snapshot WHERE is_current").fetchone()
            if not current:
                sys.exit("No current snapshot. Load a corpus first.")
            snapshot_id = current["id"]

        by_token, by_taught, all_rows = corpus_index(conn, snapshot_id)
        print(f"Corpus: snapshot {snapshot_id}, {len(all_rows)} course-lesson rows")

        text = pathlib.Path(args.csv).read_text(encoding="utf-8-sig")
        legacy = list(csv.DictReader(text.splitlines()))
        print(f"Legacy file: {len(legacy)} rows\n")

        # --- do the standards exist? ----------------------------------
        frameworks = {r["state"] for r in legacy if r.get("state")}
        sets = {r["standard_set"] for r in legacy if r.get("standard_set")}
        print(f"Claims against {'/'.join(sorted(frameworks))} "
              f"{'/'.join(sorted(sets))}")

        known = {}
        for framework in frameworks:
            for standard_set in sets:
                found = conn.execute("""
                    SELECT s.identifier, s.grade_band, s.concept
                      FROM standard s JOIN standards_set ss ON ss.id = s.set_id
                     WHERE ss.framework = %s AND ss.standard_set = %s
                """, (framework, standard_set)).fetchall()
                for f in found:
                    known[f["identifier"]] = f
        print(f"  the store holds {len(known)} standards for that set")

        used = collections.Counter(r["standard_id"] for r in legacy)
        missing = sorted(i for i in used if i not in known)
        print(f"  the file uses {len(used)} distinct standards")
        if missing:
            print(f"  {len(missing)} do not exist in the store:")
            for identifier in missing:
                print(f"    {identifier}  ({used[identifier]} rows)")
        else:
            print("  every standard id resolves")
        unused = sorted(i for i in known if i not in used)
        print(f"  {len(unused)} standards in the set are never claimed")

        # --- do the lessons exist? ------------------------------------
        resolved, unresolved = [], []
        how = collections.Counter()
        for row in legacy:
            lesson, method = resolve(row, by_token, by_taught)
            if lesson is None:
                unresolved.append((row, method))
                continue
            how[method] += 1
            resolved.append({
                "standard_id": row["standard_id"],
                "semester": row["semester"], "unit": row["unit"],
                "lesson_ref": row["lesson"],
                "stable_id": lesson["stable_id"],
                "lesson_name": lesson["lesson_name"],
                "script_name": lesson["script_name"],
                "lesson_group_name": lesson["lesson_group_name"],
                "matched_by": method,
                "standard_exists": row["standard_id"] in known,
            })

        print(f"\nResolved {len(resolved)} of {len(legacy)} rows to a lesson")
        for method, n in how.most_common():
            print(f"  {n:>4}  by {method}")
        if unresolved:
            print(f"\n{len(unresolved)} rows did not resolve:")
            grouped = collections.Counter(
                (r.get("semester"), r.get("unit"), r.get("lesson"), why)
                for r, why in unresolved)
            for (sem, unit, lesson, why), n in grouped.most_common(15):
                print(f"  {n:>3}x  {sem} unit {unit} lesson {lesson} — {why}")

        # --- what does it claim? --------------------------------------
        lessons_claimed = {r["stable_id"] for r in resolved}
        print(f"\nThe file touches {len(lessons_claimed)} distinct lessons")
        per_lesson = collections.Counter(r["stable_id"] for r in resolved)
        heavy = [(k, v) for k, v in per_lesson.most_common() if v >= 6]
        print(f"  {len(heavy)} lessons carry 6 or more standards "
              f"(the skill calls 1-3 normal)")
        for stable_id, n in heavy[:8]:
            print(f"    {n:>2}  {stable_id[:64]}")

        shells = [r for r in resolved
                  if r["lesson_group_name"]
                  and "Alternate" in r["lesson_group_name"]]
        if shells:
            print(f"\n  {len(shells)} rows land on an alternate progression")

        if args.out:
            pathlib.Path(args.out).write_text(
                json.dumps(resolved, indent=2, ensure_ascii=False),
                encoding="utf-8")
            print(f"\nWrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
