"""Read-only inputs for the comparison; baseline snapshot is pinned by its run."""
import json
from pathlib import Path

TABLES = ("run", "course", "course_unit", "lesson", "unit", "snapshot", "standard",
          "standards_set", "alignment_record", "standard_outcome")


def load(dataset=None, dsn=None):
    if dataset:
        data = json.loads(Path(dataset).read_text(encoding="utf-8"))
        for table in TABLES:
            if not isinstance(data.get(table), list):
                raise ValueError(f"Missing dataset table {table}")
        return data
    if not dsn:
        raise ValueError("Supply --dataset or set DATABASE_URL to an isolated restored database.")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return {table: conn.execute(f'SELECT * FROM "{table}"').fetchall() for table in TABLES}


def select(data, run_id):
    run = next((r for r in data["run"] if r["id"] == run_id), None)
    if not run:
        raise ValueError(f"No baseline run {run_id}")
    snapshot = next(s for s in data["snapshot"] if s["id"] == run["snapshot_id"])
    course = next(c for c in data["course"] if c["id"] == run["course_id"])
    standards_set = next(s for s in data["standards_set"] if s["id"] == run["set_id"])
    all_standards = [s for s in data["standard"] if s["set_id"] == run["set_id"]
                     and s.get("hierarchy_role") != "umbrella"]
    stored_outcomes = [o for o in data["standard_outcome"] if o["run_id"] == run_id]
    # An imported mapping may not have outcomes. Its scope is unresolved until
    # explicitly chosen; whole-set fallback is labelled, never inferred from prose.
    in_scope = {o["standard_id"] for o in stored_outcomes if o.get("in_scope")}
    standards = [s for s in all_standards if not stored_outcomes or s["id"] in in_scope]
    if not standards:
        raise ValueError("Baseline has no in-scope candidate standards.")
    units = {u["id"]: u for u in data["unit"] if u["snapshot_id"] == run["snapshot_id"]}
    memberships = {cu["unit_id"]: cu["position"] for cu in data["course_unit"]
                   if cu["course_id"] == run["course_id"]}
    lessons = [{**l, "script_name": units[l["unit_id"]]["script_name"],
                "unit_name": units[l["unit_id"]]["unit_name"],
                "unit_position": memberships[l["unit_id"]]}
               for l in data["lesson"] if l["snapshot_id"] == run["snapshot_id"]
               and l["unit_id"] in units and l["unit_id"] in memberships]
    lessons.sort(key=lambda l: (l["unit_position"], l["absolute_position"], l["id"]))
    if not lessons:
        raise ValueError("No lessons resolve to the baseline's course and snapshot.")
    return {"run": run, "snapshot": snapshot, "course": course, "standards_set": standards_set,
            "standards": standards, "lessons": lessons, "baseline_outcomes": stored_outcomes,
            "baseline_claims": [r for r in data["alignment_record"] if r["run_id"] == run_id],
            "scope_origin": "stored_outcomes" if stored_outcomes else "whole_set_fallback"}
