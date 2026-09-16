#!/usr/bin/env python3
"""Diff a run against a hand-made mapping, and say why each difference exists.

    python3 service/reconcile.py --run 3 --csv legacy.csv --out report.md

The skill's rule: run the forward evaluation independently **first**, then
diff. This does the diff only — it never reads the legacy file before the run,
so the run cannot be anchored by it.

Three buckets come out:

  both        the run and the file agree a standard belongs on a lesson
  run only    the run claims it and the file does not
  file only   the file claims it and the run does not

**The third bucket is not a list of misses.** A hand mapping and this pipeline
disagree by construction: the prior work tagged standards to lessons by topic,
and this tags them by the cognitive verb and by where the student performs the
activity. Most placement disagreements are that difference, not an error in
either. So every `file only` pair is reported with what the run said about that
standard on that lesson — usually an explicit rejection with a reason — and the
reader decides.

A mapping with no mastery column is a correlation list, not a rating. When that
is what it holds, the comparison is set overlap and this says so rather than
inventing agreement on levels nobody recorded.
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

from service.import_legacy import corpus_index, resolve           # noqa: E402

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Diff a run against a hand mapping.")
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--rejections", default=None,
                    help="the run's JSON output, for the rejection reasons")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        run = conn.execute("""
            SELECT r.*, ss.framework, ss.standard_set, c.course_name
              FROM run r JOIN standards_set ss ON ss.id = r.set_id
              JOIN course c ON c.id = r.course_id
             WHERE r.id = %s""", (args.run,)).fetchone()
        if not run:
            sys.exit(f"No run {args.run}.")

        mine = conn.execute("""
            SELECT ar.lesson_stable_id, s.identifier, ar.level, ar.evidence,
                   ar.note, ar.flags
              FROM alignment_record ar JOIN standard s ON s.id = ar.standard_id
             WHERE ar.run_id = %s""", (args.run,)).fetchall()
        mine_pairs = {(r["lesson_stable_id"], r["identifier"]): r for r in mine}

        outcomes = {r["identifier"]: r["outcome"] for r in conn.execute("""
            SELECT s.identifier, o.outcome FROM standard_outcome o
              JOIN standard s ON s.id = o.standard_id
             WHERE o.run_id = %s""", (args.run,)).fetchall()}

        by_token, by_taught, _ = corpus_index(conn, run["snapshot_id"])

        text = pathlib.Path(args.csv).read_text(encoding="utf-8-sig")
        legacy_rows = list(csv.DictReader(text.splitlines()))
        has_mastery = any((r.get("mastery") or "").strip() for r in legacy_rows)

        # Only compare on the lessons this run actually covered.
        covered = {r["lesson_stable_id"] for r in mine} | set(
            conn.execute("""
                SELECT l.stable_id FROM lesson l
                  JOIN course_unit cu ON cu.unit_id = l.unit_id
                 WHERE cu.course_id = %s AND l.snapshot_id = %s
                   AND l.has_lesson_plan""",
                (run["course_id"], run["snapshot_id"])).fetchall() and
            [r["stable_id"] for r in conn.execute("""
                SELECT l.stable_id FROM lesson l
                  JOIN course_unit cu ON cu.unit_id = l.unit_id
                 WHERE cu.course_id = %s AND l.snapshot_id = %s
                   AND l.has_lesson_plan""",
                (run["course_id"], run["snapshot_id"])).fetchall()])

        theirs, unresolved = set(), []
        for row in legacy_rows:
            lesson, method = resolve(row, by_token, by_taught)
            if lesson is None:
                unresolved.append((row, method))
                continue
            if lesson["stable_id"] not in covered:
                continue
            theirs.add((lesson["stable_id"], row["standard_id"]))

    rejections = {}
    if args.rejections and pathlib.Path(args.rejections).exists():
        data = json.loads(pathlib.Path(args.rejections).read_text(encoding="utf-8"))
        for stable_id, items in (data.get("rejections") or {}).items():
            for item in items:
                rejections[(stable_id, item["standard_id"])] = item

    ours = set(mine_pairs)
    both = ours & theirs
    run_only = ours - theirs
    file_only = theirs - ours

    lines = [f"# Reconciliation — run {args.run}", "",
             f"**Course:** {run['course_name']}",
             f"**Standards:** {run['framework']} · {run['standard_set']}",
             f"**Scope:** {run['scope_note']}", ""]
    if not has_mastery:
        lines += ["> The hand mapping carries no mastery column, so it is a "
                  "correlation list rather than a rating. This compares which "
                  "standards land on which lessons, and nothing about level.", ""]

    lines += ["## Overlap", "",
              f"| | pairs |", "|---|---|",
              f"| both agree | {len(both)} |",
              f"| run only | {len(run_only)} |",
              f"| hand mapping only | {len(file_only)} |", ""]
    denom = len(ours | theirs) or 1
    lines.append(f"Agreement on {len(both)} of {denom} pairs "
                 f"({100*len(both)//denom}%).")
    lines.append("")
    lines.append("A hand mapping tags by topic; this run tags by the cognitive "
                 "verb and by where the student performs the activity. That "
                 "difference, not an error on either side, explains most of "
                 "what follows.")
    lines.append("")

    # --- what the run says about the pairs only the file has ------------
    kinds = collections.Counter()
    for pair in file_only:
        rejection = rejections.get(pair)
        kinds[rejection["kind"] if rejection else "never considered"] += 1

    lines += ["## What the run said about the pairs only the hand mapping has",
              "", "| the run's reason | pairs |", "|---|---|"]
    for kind, n in kinds.most_common():
        lines.append(f"| {kind.replace('_', ' ')} | {n} |")
    lines += ["",
              "`never considered` means the standard was not close enough to "
              "the lesson for the run to weigh it at all.", ""]

    lines += ["### Examples, with the reason given", ""]
    shown = 0
    for pair in sorted(file_only):
        rejection = rejections.get(pair)
        if not rejection or shown >= 12:
            continue
        lines.append(f"- **{pair[1]}** on `{pair[0].split('::')[-1]}` — "
                     f"*{rejection['kind'].replace('_',' ')}*: "
                     f"{rejection['reason']}")
        shown += 1
    lines.append("")

    lines += ["## Pairs only the run has", "",
              "These are claims with named evidence that the hand mapping does "
              "not carry.", ""]
    for pair in sorted(run_only)[:15]:
        record = mine_pairs[pair]
        lines.append(f"- **{pair[1]}** ({record['level']}) on "
                     f"`{pair[0].split('::')[-1]}` — {record['evidence'][:150]}")
    if len(run_only) > 15:
        lines.append(f"- …and {len(run_only)-15} more")
    lines.append("")

    # --- standard-level agreement --------------------------------------
    their_standards = {s for _, s in theirs}
    our_standards = {s for _, s in ours}
    lines += ["## Which standards each finds at all", "",
              f"- both: {len(their_standards & our_standards)}",
              f"- hand mapping only: {len(their_standards - our_standards)}"
              f" — {', '.join(sorted(their_standards - our_standards)) or 'none'}",
              f"- run only: {len(our_standards - their_standards)}"
              f" — {', '.join(sorted(our_standards - their_standards)) or 'none'}",
              ""]

    if unresolved:
        lines += ["## Rows in the hand mapping that name no lesson", ""]
        grouped = collections.Counter(
            (r.get("semester"), r.get("unit"), r.get("lesson"), why)
            for r, why in unresolved)
        for (sem, unit, lesson, why), n in grouped.most_common():
            lines.append(f"- {n}x {sem} unit {unit} lesson {lesson} — {why}")
        lines.append("")

    report = "\n".join(lines)
    if args.out:
        pathlib.Path(args.out).write_text(report, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
