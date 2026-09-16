#!/usr/bin/env python3
"""Run a forward alignment: one course against one standards set.

    python3 service/align.py --set 3 --course 2 --scope "All concepts, grades 9-12"
    python3 service/align.py --set 3 --course 2 --scope "..." --limit 5   # pilot

Writes a `run`, one `alignment_record` per surviving (standard, lesson) claim,
and one `standard_outcome` per candidate standard **including the misses** —
which is what lets the store answer "what percentage do you cover".

Nothing is approved. Every record lands as `proposed` and goes to the review
queue, because a drafted boundary is a hypothesis about a state's intent and no
run should publish on its own.

**Cost.** Every lesson is one model call. `--limit` runs a pilot first; the
measured cost per lesson is printed so the full run is a decision rather than a
surprise. The standards set is in the cached prefix, so the marginal cost of a
lesson is the lesson itself.
"""
import argparse
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from service.app.alignment import engine, verify                  # noqa: E402
from service.app.curriculum.distil import distil                  # noqa: E402

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")


def fetch_standards(conn, set_id):
    rows = conn.execute("""
        SELECT identifier, statement, concept, subconcept, grade_band, level,
               boundary_includes, boundary_excludes, keywords,
               boundary_provenance, hierarchy_role, addressability
          FROM standard WHERE set_id = %s ORDER BY id""", (set_id,)).fetchall()
    # Umbrella rows are rated by rollup from their children, never on their
    # own. Counting them as well double-counts every coverage percentage.
    return [r for r in rows if r["hierarchy_role"] != "umbrella"]


def fetch_lessons(conn, course_id, snapshot_id, limit=None, taught_only=True):
    rows = conn.execute("""
        SELECT l.id, l.stable_id, l.lesson_name, l.lesson_key, l.lesson_token,
               l.relative_position, l.absolute_position, l.content_hash,
               l.has_lesson_plan, l.has_objectives, l.lesson_group_name,
               l.plan, l.levels, u.script_name, u.unit_name, cu.position AS unit_position
          FROM lesson l
          JOIN unit u ON u.id = l.unit_id
          JOIN course_unit cu ON cu.unit_id = u.id
         WHERE cu.course_id = %(course)s AND l.snapshot_id = %(snap)s
         ORDER BY cu.position, l.absolute_position""",
        {"course": course_id, "snap": snapshot_id}).fetchall()
    if taught_only:
        # An assessment shell has no plan and no objective to anchor a forward
        # claim on. It is skipped, and said to be skipped.
        rows = [r for r in rows if r["has_lesson_plan"]]
    return rows[:limit] if limit else rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run a forward alignment.")
    ap.add_argument("--set", type=int, required=True, help="standards_set id")
    ap.add_argument("--course", type=int, required=True, help="course id")
    ap.add_argument("--scope", required=True,
                    help="which concepts and grades. Required: a percentage "
                         "without its scope beside it is a wrong number.")
    ap.add_argument("--grades", default=None,
                    help="filter candidates to bands overlapping these grades")
    ap.add_argument("--limit", type=int, default=None, help="pilot on N lessons")
    ap.add_argument("--model", default=engine.MODEL)
    ap.add_argument("--dry-run", action="store_true",
                    help="build the prompts, call nothing, report the size")
    ap.add_argument("--out", default=None, help="also write the run as JSON")
    args = ap.parse_args(argv)

    if not args.dry_run and not engine.load_key():
        sys.exit("No ANTHROPIC_API_KEY. Put it in service/.env or export it.")

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        standards_set = conn.execute(
            "SELECT * FROM standards_set WHERE id = %s", (args.set,)).fetchone()
        if not standards_set:
            sys.exit(f"No standards set {args.set}.")
        course = conn.execute(
            "SELECT * FROM course WHERE id = %s", (args.course,)).fetchone()
        if not course:
            sys.exit(f"No course {args.course}.")
        snapshot_id = course["snapshot_id"]

        all_standards = fetch_standards(conn, args.set)
        candidates, filter_note = engine.candidate_standards(
            all_standards, args.grades)
        candidate_ids = [s["identifier"] for s in candidates]
        lessons = fetch_lessons(conn, args.course, snapshot_id, args.limit)

        print(f"Standards : {standards_set['framework']}/"
              f"{standards_set['standard_set']}/{standards_set['framework_year']}"
              f" — {len(candidates)} candidates"
              + (f" (filtered from {len(all_standards)})"
                 if filter_note.get("filtered") else ""))
        print(f"Course    : {course['course_name']}  ({len(lessons)} taught lessons)")
        print(f"Scope     : {args.scope}")
        print(f"Model     : {args.model}")
        if standards_set["boundary_provenance"] == "drafted":
            print("NOTE      : these boundaries are drafted and unreviewed. A "
                  "rejection on a boundary may be the boundary's fault.")

        standards_text = engine.standards_block(candidates)

        if args.dry_run:
            import anthropic
            engine.load_key()
            client = anthropic.Anthropic()
            sample = engine.lesson_block(lessons[0], distil(lessons[0]))
            counted = client.messages.count_tokens(
                model=args.model,
                system=[{"type": "text", "text": engine.RULES},
                        {"type": "text", "text": standards_text}],
                messages=[{"role": "user", "content": sample}])
            print(f"\nDry run. Prompt is {counted.input_tokens:,} tokens for "
                  f"the first lesson.")
            print(f"  cached prefix ~{len(standards_text)//4:,} tokens, "
                  f"read once per lesson after the first")
            return 0

        import anthropic
        client = anthropic.Anthropic()

        run_id = conn.execute("""
            INSERT INTO run (set_id, course_id, snapshot_id, scope_note, grain)
            VALUES (%s, %s, %s, %s, 'lesson') RETURNING id""",
            (args.set, args.course, snapshot_id, args.scope)).fetchone()["id"]
        conn.commit()
        print(f"\nRun {run_id} created.\n")

        usage, per_claims, per_rejections = {}, {}, {}
        failures = []
        started = time.time()

        for i, lesson in enumerate(lessons, 1):
            distilled = distil(lesson)
            try:
                answer = engine.judge(client, standards_text, lesson, distilled,
                                      model=args.model, usage=usage)
            except Exception as exc:                              # noqa: BLE001
                failures.append({"stable_id": lesson["stable_id"],
                                 "error": f"{type(exc).__name__}: {exc}"})
                print(f"  [{i}/{len(lessons)}] {lesson['lesson_name'][:44]:44} "
                      f"FAILED {type(exc).__name__}")
                continue

            kept, dropped = verify.verify_lesson(
                answer.get("claims", []), answer.get("considered_and_rejected", []),
                candidate_ids, lesson, distilled)
            per_claims[lesson["stable_id"]] = kept
            per_rejections[lesson["stable_id"]] = dropped

            for claim in kept:
                standard_id = conn.execute(
                    "SELECT id FROM standard WHERE set_id=%s AND identifier=%s",
                    (args.set, claim["standard_id"])).fetchone()
                if not standard_id:
                    continue
                conn.execute("""
                    INSERT INTO alignment_record
                      (run_id, standard_id, lesson_id, lesson_stable_id,
                       lesson_content_hash, level, evidence, note,
                       is_choice_level, choice_option, flags, review_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'proposed')
                    ON CONFLICT (run_id, standard_id, lesson_id) DO NOTHING""",
                    (run_id, standard_id["id"], lesson["id"], lesson["stable_id"],
                     lesson["content_hash"], claim["level"], claim["evidence"],
                     claim["note"], claim["is_choice_level"],
                     claim["choice_option"], json.dumps(claim["flags"])))
            conn.commit()

            spend = engine.cost_of(usage, args.model)
            print(f"  [{i}/{len(lessons)}] {lesson['lesson_name'][:44]:44} "
                  f"{len(kept):>2} claims, {len(dropped):>2} rejected   "
                  f"${spend:.2f}")

        # --- outcomes, including the misses --------------------------------
        outcomes = verify.aggregate(per_claims, per_rejections, candidate_ids)
        for identifier, outcome in outcomes.items():
            standard_id = conn.execute(
                "SELECT id FROM standard WHERE set_id=%s AND identifier=%s",
                (args.set, identifier)).fetchone()
            if not standard_id:
                continue
            conn.execute("""
                INSERT INTO standard_outcome
                  (run_id, standard_id, outcome, in_scope, rationale)
                VALUES (%s,%s,%s,true,%s)
                ON CONFLICT (run_id, standard_id) DO UPDATE
                   SET outcome = EXCLUDED.outcome,
                       rationale = EXCLUDED.rationale""",
                (run_id, standard_id["id"], outcome["outcome"],
                 outcome["rationale"]))
        conn.commit()

        check = verify.count_check(outcomes, candidate_ids)
        cover = verify.coverage(outcomes)
        spend = engine.cost_of(usage, args.model)

        print(f"\nRun {run_id} finished in {time.time()-started:.0f}s")
        print(f"  claims kept      {sum(len(c) for c in per_claims.values()):>6}")
        print(f"  rejections       {sum(len(r) for r in per_rejections.values()):>6}")
        print(f"  coverage         {cover['addressed']}/{cover['total']} "
              f"({cover['percent']}%)  — scope: {args.scope}")
        print(f"  count check      {'balances' if check['balances'] else 'DOES NOT BALANCE'}")
        for outcome, n in sorted(check["by_outcome"].items()):
            print(f"    {outcome:<26} {n:>4}")
        if failures:
            print(f"  lessons that failed: {len(failures)}")
            for f in failures[:5]:
                print(f"    {f['stable_id']}: {f['error']}")
        print(f"\n  spend            ${spend:.2f}  "
              f"({usage.get('calls',0)} calls, "
              f"{usage.get('cache_read_input_tokens',0):,} cached tokens read)")
        if lessons:
            print(f"  per lesson       ${spend/max(1,len(lessons)):.3f}")

        if args.out:
            pathlib.Path(args.out).write_text(json.dumps({
                "run_id": run_id, "scope": args.scope, "model": args.model,
                "claims": per_claims, "rejections": per_rejections,
                "outcomes": outcomes, "count_check": check,
                "coverage": cover, "usage": usage, "cost_usd": spend,
                "failures": failures}, indent=2, ensure_ascii=False),
                encoding="utf-8")
            print(f"  wrote {args.out}")

        print("\nEvery record is `proposed`. Nothing is approved and nothing "
              "is public.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
