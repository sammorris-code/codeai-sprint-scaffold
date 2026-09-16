#!/usr/bin/env python3
"""Export one or more runs as the mapping CSV the viewer reads.

    python3 service/export_mapping.py --runs 3:S1,4:S2 --course-code AIF

One row per (standard, lesson) pair. The file name is
`COURSE_FRAMEWORK_SET_YEAR_mapping.csv`, and its canonical home is
`mapped_standards/`. The aggregate `All_*` files a viewer reads are made by
concatenating these; never hand-edit either.

**One file per course x standards set, with every semester inside it.** The
file name carries no semester, so exporting S1 and S2 as separate commands
silently overwrote the first — which is why `--runs` takes them together.

**`mastery` is rebuilt here, not stored per row.** The old CSV repeated the
aggregate rating on every contributing row, which meant two rows could disagree
about the same standard. The store keeps the aggregate once, in
`standard_outcome`, and this join puts it back. It is the rating across the
whole course, so a row may read `Mastered` while its own note explains that
this lesson contributes at a lower level — that is the column's meaning, not a
contradiction.

Column rules that are easy to get wrong, all from the briefing:

- `state` holds the framework, not a US state. `CSTA` is a valid value.
- `unit` is the number alone. `6`, never `S1-U6`.
- `lesson` is a bare token with no `L` prefix, so a viewer can render a
  `unit.lesson` pill. Non-numeric tokens such as `capstone` are allowed and
  must sort after the numeric ones.
- `semester` is its own column and is never fused into `unit`.
"""
import argparse
import csv
import io
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")

COLUMNS = ["year", "state", "standard_set", "set_type", "standard_id", "course",
           "semester", "unit", "lesson", "mastery", "evidence", "note"]

MASTERY_LABEL = {"introduced": "Introduced", "developed": "Developed",
                 "mastered": "Mastered"}

RECORDS_SQL = """
    SELECT s.identifier, ar.evidence, ar.note, ar.level,
           ar.is_choice_level, ar.choice_option, ar.flags,
           o.outcome AS aggregate,
           l.lesson_token, cu.position AS unit_position,
           u.script_name, l.lesson_group_name
      FROM alignment_record ar
      JOIN standard s ON s.id = ar.standard_id
      JOIN lesson l ON l.id = ar.lesson_id
      JOIN unit u ON u.id = l.unit_id
      JOIN course_unit cu ON cu.unit_id = u.id AND cu.course_id = %(course)s
      LEFT JOIN standard_outcome o ON o.run_id = ar.run_id
                                  AND o.standard_id = ar.standard_id
     WHERE ar.run_id = %(run)s {status}
     ORDER BY cu.position, l.absolute_position
"""


def sort_key(row):
    """Numeric lessons first, in order; named ones after, alphabetically."""
    token = str(row["lesson"])
    unit = str(row["unit"])
    return (str(row["semester"]),
            int(unit) if unit.isdigit() else 999,
            0 if token.isdigit() else 1,
            int(token) if token.isdigit() else 0,
            token, row["standard_id"])


def notes_for(row):
    notes = []
    if row["note"]:
        notes.append(row["note"])
    if row["is_choice_level"]:
        option = f" ({row['choice_option']})" if row["choice_option"] else ""
        notes.append("optional pathway capped at Introduced" + option)
    for flag in (row["flags"] or []):
        if flag.get("kind") == "artifact_mismatch":
            notes.append("artifact caveat")
        if flag.get("kind") == "overclaim":
            notes.append("lesson carries many standards")
    group = row["lesson_group_name"] or ""
    if "Alternate" in group:
        notes.append("alternate progression - do not also credit the "
                     "Content lesson")
    return "; ".join(notes)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Export runs as one mapping CSV.")
    ap.add_argument("--runs", required=True,
                    help="run:semester pairs, e.g. 3:S1,4:S2 — or just 3 for "
                         "a single-semester course")
    ap.add_argument("--course-code", required=True, help="e.g. AIF")
    ap.add_argument("--out-dir", default="mapped_standards")
    ap.add_argument("--only-accepted", action="store_true",
                    help="export only records a reviewer has accepted")
    args = ap.parse_args(argv)

    wanted = []
    for part in args.runs.split(","):
        part = part.strip()
        if part:
            run_id, _, semester = part.partition(":")
            wanted.append((int(run_id), semester))

    status = "AND ar.review_status = 'accepted'" if args.only_accepted else ""
    out, identity = [], None

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        for run_id, semester in wanted:
            run = conn.execute("""
                SELECT r.course_id, ss.framework, ss.standard_set, ss.set_type,
                       ss.framework_year
                  FROM run r JOIN standards_set ss ON ss.id = r.set_id
                 WHERE r.id = %s""", (run_id,)).fetchone()
            if not run:
                sys.exit(f"No run {run_id}.")
            here = (run["framework"], run["standard_set"], run["framework_year"])
            if identity and here != identity:
                sys.exit("All runs in one file must share a standards set: "
                         f"{identity} vs {here}.")
            identity = here

            rows = conn.execute(RECORDS_SQL.format(status=status),
                                {"run": run_id,
                                 "course": run["course_id"]}).fetchall()
            for row in rows:
                out.append({
                    "year": run["framework_year"],
                    "state": run["framework"],
                    "standard_set": run["standard_set"],
                    "set_type": run["set_type"],
                    "standard_id": row["identifier"],
                    "course": args.course_code,
                    "semester": semester,
                    "unit": row["unit_position"],
                    "lesson": row["lesson_token"],
                    "mastery": MASTERY_LABEL.get(
                        row["aggregate"] or row["level"], ""),
                    "evidence": (row["evidence"] or "")[:300],
                    "note": notes_for(row),
                })
            print(f"  run {run_id} ({semester or 'no semester'}): "
                  f"{len(rows)} rows")

    out.sort(key=sort_key)

    framework, standard_set, year = identity
    name = (f"{args.course_code}_{framework}_{standard_set}_{year}_mapping.csv")
    directory = pathlib.Path(args.out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
    path.write_text(buf.getvalue(), encoding="utf-8")

    print(f"\nWrote {path} — {len(out)} rows")
    print(f"  {len({r['standard_id'] for r in out})} distinct standards")
    print(f"  {len({(r['semester'], r['unit'], r['lesson']) for r in out})} "
          f"distinct lessons")
    print(f"  semesters: {', '.join(sorted({r['semester'] or '-' for r in out}))}")
    if args.only_accepted:
        print("  accepted records only")
    else:
        print("  NOTE: includes records nobody has reviewed. Pass "
              "--only-accepted for a district-facing file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
