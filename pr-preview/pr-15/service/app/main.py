"""The Standards service.

Two surfaces on one app, and the split is enforced here rather than in any
interface:

    /api      staff. Everything, drafts included.
    /public   districts. Approved records from reviewed sets only.

A /public endpoint cannot return an unapproved record whatever it is asked for.
An interface bug must never be able to leak a draft to a school district.

Every response shape here matches a file in contract/fixtures/. That is not a
coincidence and it is not decoration: service/test_contract.py compares the two
and fails if they drift. It is what lets the interface be built against the
fixtures and then pointed at this service with one line changed.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .db import pool, rows, one, execute


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open()
    yield
    pool.close()


app = FastAPI(title="Standards service", version="0.1.0", lifespan=lifespan)

# The interface is served as static files from somewhere else, so it is a
# different origin. Prototype setting: tighten before this leaves a laptop.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


def fail(status, code, message, field=None):
    raise HTTPException(status_code=status,
                        detail={"error": {"code": code, "message": message,
                                          "field": field}})


# ---------------------------------------------------------------------------
# Standards sets
# ---------------------------------------------------------------------------

SET_COLUMNS = """
    id, framework, standard_set, set_type, framework_year, title, source, scope,
    standard_count, boundary_provenance, schema_notes, supersedes, superseded_by,
    reviewed_by, reviewed_on, created_at,
    (boundary_provenance = 'drafted+reviewed') AS publishable
"""


@app.get("/api/standards-sets")
def list_standards_sets(framework: str | None = None, set_type: str | None = None):
    """The registry. This is what replaced the hardcoded state list on the page.

    publishable is computed here, from boundary_provenance, and never stored.
    One rule, one place. No interface re-derives it.
    """
    items = rows(f"""SELECT {SET_COLUMNS} FROM standards_set
                     WHERE (%(framework)s::text IS NULL OR framework = %(framework)s)
                       AND (%(set_type)s::text IS NULL OR set_type = %(set_type)s)
                     ORDER BY framework, standard_set, framework_year""",
                 {"framework": framework, "set_type": set_type})
    return {"items": items, "total": len(items)}


@app.get("/api/standards-sets/{set_id}/standards")
def list_standards(set_id: int):
    items = rows("""SELECT id, set_id, identifier, statement, concept, subconcept,
                           grade_band, level, boundary_includes, boundary_excludes,
                           keywords, boundary_provenance, nearest_csta,
                           hierarchy_role, rating_rule, addressability, parent_id,
                           extras
                    FROM standard WHERE set_id = %(id)s ORDER BY id""",
                 {"id": set_id})
    if not items:
        fail(404, "not_found", f"No standards set with id {set_id}.", "set_id")
    return {"items": items, "total": len(items)}


class IngestRequest(BaseModel):
    """The identity trio is required, and there is no default for any of it.

    This is the correction the whole contract exists to make. The old schema
    turned a file that lost its identity into a CSTA 2026 file in silence, so a
    wrong label could reach a district. Missing identity is now an error.
    """
    filename: str
    framework: str = Field(min_length=1)
    standard_set: str = Field(min_length=1)
    set_type: str = Field(pattern="^(standards|course_objectives)$")
    framework_year: str = Field(min_length=4)


@app.post("/api/standards-sets", status_code=202)
def ingest(req: IngestRequest):
    """Characterizes a document and waits for the user to confirm scope.

    Writes nothing. The engine that reads the document is a separate build; this
    endpoint exists so the interface has the real shape to work against.
    """
    return {"proposed": req.model_dump(exclude={"filename"}),
            "awaiting": "scope_confirmation",
            "count_reconciled": None,
            "warnings": ["The ingestion engine is not built yet. "
                         "This endpoint validates identity and returns the shape."]}


# ---------------------------------------------------------------------------
# Curriculum. Read-only, always. Nothing here ever writes upstream.
# ---------------------------------------------------------------------------

@app.get("/api/snapshots")
def list_snapshots():
    items = rows("""SELECT id, source_repo, source_branch, source_commit,
                           extracted_at, is_current, lesson_count, notes
                    FROM snapshot ORDER BY extracted_at DESC""")
    return {"items": items, "total": len(items)}


@app.get("/api/courses")
def list_courses(snapshot_id: int | None = None):
    """Units come back nested, ordered by position.

    position and displayed_number are both returned and they are not the same
    thing. One real course leaves its first four units blank and numbers the
    last two 1 and 2. Sort by position. Show displayed_number. Never compute
    one from the other.
    """
    items = rows("""
        SELECT c.id, c.snapshot_id, c.course_key, c.course_name,
               COALESCE(json_agg(json_build_object(
                   'id', u.id, 'script_name', u.script_name,
                   'unit_name', u.unit_name, 'position', cu.position,
                   'displayed_number', cu.displayed_number,
                   'lesson_count', (SELECT count(*) FROM lesson l WHERE l.unit_id = u.id)
               ) ORDER BY cu.position) FILTER (WHERE u.id IS NOT NULL), '[]') AS units
        FROM course c
        LEFT JOIN course_unit cu ON cu.course_id = c.id
        LEFT JOIN unit u ON u.id = cu.unit_id
        WHERE (%(snap)s::int IS NULL OR c.snapshot_id = %(snap)s)
        GROUP BY c.id ORDER BY c.id""", {"snap": snapshot_id})
    return {"items": items, "total": len(items)}


LESSON_JSON = """json_build_object(
    'stable_id', l.stable_id, 'lesson_key', l.lesson_key,
    'lesson_name', l.lesson_name, 'lesson_token', l.lesson_token,
    'script_name', u.script_name, 'unit_name', u.unit_name,
    'displayed_number', cu.displayed_number, 'position', cu.position,
    'relative_position', l.relative_position,
    'absolute_position', l.absolute_position,
    'has_lesson_plan', l.has_lesson_plan, 'has_objectives', l.has_objectives,
    'content_hash', l.content_hash,
    'objectives', l.plan->'objectives',
    'duration_minutes', l.plan->'duration_minutes')"""


@app.get("/api/lessons")
def list_lessons(course_id: int | None = None):
    items = rows(f"""
        SELECT l.id, {LESSON_JSON} AS lesson
        FROM lesson l
        JOIN unit u ON u.id = l.unit_id
        LEFT JOIN course_unit cu ON cu.unit_id = u.id
        WHERE (%(course)s::int IS NULL OR cu.course_id = %(course)s)
        ORDER BY l.absolute_position""", {"course": course_id})
    return {"items": [dict(r["lesson"], id=r["id"]) for r in items],
            "total": len(items)}


# ---------------------------------------------------------------------------
# Runs and review
# ---------------------------------------------------------------------------

def run_or_404(run_id):
    run = one("""SELECT id, set_id, course_id, snapshot_id, scope_note, grain,
                        status, previous_run_id, created_at, approved_by, approved_on
                 FROM run WHERE id = %(id)s""", {"id": run_id})
    if not run:
        fail(404, "not_found", f"No run with id {run_id}.", "run_id")
    return run


@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    run = run_or_404(run_id)
    run["counts"] = one("""
        SELECT (SELECT count(*) FROM standard_outcome WHERE run_id = %(id)s) AS standards,
               count(*) FILTER (WHERE review_status = 'proposed') AS proposed,
               count(*) FILTER (WHERE review_status = 'accepted') AS accepted,
               count(*) FILTER (WHERE review_status = 'rejected') AS rejected,
               count(*) FILTER (WHERE review_status = 'stale')    AS stale,
               count(*) FILTER (WHERE jsonb_array_length(flags) > 0) AS flagged
        FROM alignment_record WHERE run_id = %(id)s""", {"id": run_id})
    return run


@app.get("/api/runs/{run_id}/queue")
def review_queue(run_id: int, status: str | None = None, flagged: bool | None = None):
    """The main screen. One standard at a time, with its evidence.

    Standards with no evidence at all are still returned. Eight of the fourteen
    demo standards have none, for six different reasons, and a queue that drops
    them makes the totals wrong.
    """
    run_or_404(run_id)
    items = rows(f"""
        SELECT json_build_object(
                 'id', s.id, 'identifier', s.identifier, 'statement', s.statement,
                 'concept', s.concept, 'subconcept', s.subconcept,
                 'hierarchy_role', s.hierarchy_role, 'rating_rule', s.rating_rule,
                 'addressability', s.addressability,
                 'boundary_includes', s.boundary_includes,
                 'boundary_excludes', s.boundary_excludes,
                 'boundary_provenance', s.boundary_provenance) AS standard,
               json_build_object(
                 'standard_id', o.standard_id, 'outcome', o.outcome,
                 'in_scope', o.in_scope, 'rationale', o.rationale) AS outcome,
               COALESCE((
                 SELECT json_agg(json_build_object(
                          'id', r.id, 'standard_id', r.standard_id,
                          'lesson', {LESSON_JSON},
                          'level', r.level, 'evidence', r.evidence, 'note', r.note,
                          'authorship', r.authorship,
                          'is_choice_level', r.is_choice_level,
                          'choice_option', r.choice_option, 'flags', r.flags,
                          'review_status', r.review_status,
                          'reviewed_by', r.reviewed_by, 'reviewed_on', r.reviewed_on,
                          'lesson_content_hash', r.lesson_content_hash) ORDER BY r.id)
                 FROM alignment_record r
                 JOIN lesson l ON l.id = r.lesson_id
                 JOIN unit u ON u.id = l.unit_id
                 LEFT JOIN course_unit cu ON cu.unit_id = u.id
                 WHERE r.run_id = o.run_id AND r.standard_id = o.standard_id
                   AND (%(status)s::text IS NULL OR r.review_status = %(status)s)
                   AND (%(flagged)s::bool IS NULL
                        OR (jsonb_array_length(r.flags) > 0) = %(flagged)s)
               ), '[]') AS records
        FROM standard_outcome o
        JOIN standard s ON s.id = o.standard_id
        WHERE o.run_id = %(run)s
        ORDER BY s.id""",
        {"run": run_id, "status": status, "flagged": flagged})

    for item in items:
        item["counts"] = {
            "records": len(item["records"]),
            "flagged": sum(1 for r in item["records"] if r["flags"]),
        }
    return {"run_id": run_id, "items": items, "total": len(items), "cursor": None}


class Decision(BaseModel):
    review_status: str = Field(pattern="^(accepted|rejected|changed|proposed)$")
    level: str | None = Field(default=None, pattern="^(introduced|developed|mastered)$")
    actor: str
    reason: str | None = None


@app.patch("/api/records/{record_id}")
def decide(record_id: int, d: Decision):
    """One reviewer decision.

    The reviewer may change the level, not only accept or reject, because the
    proposed depth is often the thing that is wrong. Both the old and the new
    value go into review_event, so a change is visible afterwards.

    A rejection needs a reason. A rejection with no reason teaches nobody.
    """
    before = one("""SELECT id, level, review_status, is_choice_level
                    FROM alignment_record WHERE id = %(id)s""", {"id": record_id})
    if not before:
        fail(404, "not_found", f"No record with id {record_id}.", "record_id")
    if d.review_status == "rejected" and not d.reason:
        fail(422, "reason_required",
             "Rejecting a match needs a reason. A rejection with no reason "
             "teaches nobody.", "reason")

    new_level = d.level or before["level"]
    if before["is_choice_level"] and new_level != "introduced":
        fail(422, "choice_level_capped",
             "This evidence sits in a student-choice branch, so only part of the "
             "class meets it. It cannot be raised above introduced.", "level")

    execute("""UPDATE alignment_record
               SET review_status = %(status)s, level = %(level)s,
                   reviewed_by = %(actor)s, reviewed_on = now()
               WHERE id = %(id)s""",
            {"id": record_id, "status": d.review_status, "level": new_level,
             "actor": d.actor})
    execute("""INSERT INTO review_event
               (record_id, actor, action, from_value, to_value, reason)
               VALUES (%(id)s, %(actor)s, %(action)s, %(frm)s, %(to)s, %(reason)s)""",
            {"id": record_id, "actor": d.actor, "action": d.review_status,
             "frm": f"{before['review_status']}/{before['level']}",
             "to": f"{d.review_status}/{new_level}", "reason": d.reason})
    return one("""SELECT id, level, review_status, reviewed_by, reviewed_on
                  FROM alignment_record WHERE id = %(id)s""", {"id": record_id})


COVERAGE_SQL = """
    SELECT s.identifier, s.concept, o.outcome, o.in_scope, s.hierarchy_role,
           (SELECT count(*) FROM alignment_record r
             WHERE r.run_id = o.run_id AND r.standard_id = o.standard_id) AS evidence_count
    FROM standard_outcome o JOIN standard s ON s.id = o.standard_id
    WHERE o.run_id = %(run)s ORDER BY s.id"""

COVERED = ("mastered", "developed", "introduced")


def coverage_for(run_id):
    """One row for every standard, misses included.

    A mapping holds matches only, so it cannot answer "what percentage do you
    cover", which is the question states ask. This can.

    Umbrella headings are excluded from every total. They are rated by rollup
    from their children, so counting them as well double-counts.
    """
    run = run_or_404(run_id)
    all_rows = rows(COVERAGE_SQL, {"run": run_id})
    countable = [r for r in all_rows if r["hierarchy_role"] != "umbrella"]
    in_scope = [r for r in countable if r["in_scope"]]

    buckets = {k: 0 for k in ("mastered", "developed", "introduced", "not_addressed",
                              "boundary_issue", "not_curriculum_addressable")}
    for r in in_scope:
        buckets[r["outcome"]] += 1

    cov_in = sum(buckets[k] for k in COVERED)
    cov_all = sum(1 for r in countable if r["outcome"] in COVERED)
    total = sum(buckets.values())

    def pct(n, d):
        return round(100 * n / d) if d else 0

    return run, {
        "run_id": run_id,
        "scope_note": run["scope_note"],
        "in_scope": {"total": len(in_scope), "covered": cov_in,
                     "percent": pct(cov_in, len(in_scope))},
        "whole_framework": {"total": len(countable), "covered": cov_all,
                            "percent": pct(cov_all, len(countable))},
        "buckets": buckets,
        "count_check": {"sum": total, "candidate_set": len(in_scope),
                        "ok": total == len(in_scope)},
        "umbrella_excluded": len(all_rows) - len(countable),
        "rows": all_rows,
    }


@app.get("/api/runs/{run_id}/coverage")
def coverage(run_id: int):
    """Both percentages, always.

    Scope is a judgement, not a fact. Against the whole framework and against
    the part in scope are both true and they differ. Returning one number
    invites a reader to quote it without its scope.
    """
    return coverage_for(run_id)[1]


@app.post("/api/runs/{run_id}/approve")
def approve(run_id: int, actor: str):
    """The release gate.

    Two conditions, both required: the run is approved by a person, and a person
    has checked the set's boundary notes. Results built on unchecked notes
    cannot reach a district, and that is enforced here rather than by an
    interface remembering to.
    """
    run = run_or_404(run_id)
    s = one("SELECT boundary_provenance, framework, standard_set, framework_year "
            "FROM standards_set WHERE id = %(id)s", {"id": run["set_id"]})
    if s["boundary_provenance"] != "drafted+reviewed":
        fail(409, "set_not_reviewed",
             f"This run cannot be approved. The boundary notes of "
             f"{s['framework']} / {s['standard_set']} / {s['framework_year']} are "
             f"{s['boundary_provenance']} and no person has checked them.", "set_id")

    check = coverage_for(run_id)[1]["count_check"]
    if not check["ok"]:
        fail(409, "count_mismatch",
             f"The buckets sum to {check['sum']} but the candidate set holds "
             f"{check['candidate_set']}. A standard has no outcome row.", "buckets")

    execute("""UPDATE run SET status = 'approved', approved_by = %(actor)s,
               approved_on = now() WHERE id = %(id)s""",
            {"id": run_id, "actor": actor})
    return get_run(run_id)


# ---------------------------------------------------------------------------
# Public. Approved records from reviewed sets only. No parameter widens this.
# ---------------------------------------------------------------------------

PUBLISHED = """
    r.status = 'approved' AND ss.boundary_provenance = 'drafted+reviewed'
"""


@app.get("/public/standards-sets")
def public_sets():
    items = rows(f"""SELECT DISTINCT ss.id, ss.framework, ss.standard_set,
                            ss.set_type, ss.framework_year, ss.title
                     FROM standards_set ss JOIN run r ON r.set_id = ss.id
                     WHERE {PUBLISHED} ORDER BY ss.framework, ss.standard_set""")
    return {"items": items, "total": len(items)}


@app.get("/public/coverage")
def public_coverage(set_id: int, course_id: int):
    published = one(f"""SELECT r.id FROM run r JOIN standards_set ss ON ss.id = r.set_id
                        WHERE r.set_id = %(set)s AND r.course_id = %(course)s
                          AND {PUBLISHED}
                        ORDER BY r.approved_on DESC NULLS LAST LIMIT 1""",
                    {"set": set_id, "course": course_id})
    if not published:
        fail(404, "not_published",
             "No approved records exist for this set and course.")

    run, cov = coverage_for(published["id"])
    s = one("SELECT framework, standard_set, framework_year, title "
            "FROM standards_set WHERE id = %(id)s", {"id": set_id})
    c = one("SELECT course_key, course_name FROM course WHERE id = %(id)s",
            {"id": course_id})

    # Strip everything a district must not see. Done here, not in the interface.
    public_rows = [{"identifier": r["identifier"], "concept": r["concept"],
                    "outcome": r["outcome"]}
                   for r in cov["rows"]
                   if r["in_scope"] and r["hierarchy_role"] != "umbrella"]
    return {"set": s, "course": c, "scope_note": cov["scope_note"],
            "in_scope": cov["in_scope"], "whole_framework": cov["whole_framework"],
            "buckets": cov["buckets"], "rows": public_rows}


@app.get("/health")
def health():
    return {"ok": one("SELECT 1 AS ok")["ok"] == 1}
