"""Internal proposed-run browsing and review. Deliberately no public endpoint."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from ..db import rows, one, pool

router = APIRouter(prefix="/api/evidence-runs", tags=["Evidence workflow"])


@router.get("")
def list_runs():
    if not one("SELECT to_regclass('public.evidence_run') AS name")["name"]:
        return {"items": [], "migration_required": True}
    return {"items": rows("""SELECT id, baseline_run_id, status, created_at,
             payload->'manifest'->>'course_name' AS course_name,
             payload->'manifest'->>'mode' AS mode FROM evidence_run ORDER BY id DESC""")}


@router.get("/{run_id}")
def get_run(run_id: int):
    record = one("SELECT id, status, payload FROM evidence_run WHERE id=%(id)s", {"id": run_id})
    if not record:
        raise HTTPException(404, "Evidence run not found")
    record["reviews"] = rows("SELECT * FROM evidence_review WHERE evidence_run_id=%(id)s ORDER BY id", {"id": run_id})
    return record


class Review(BaseModel):
    source_fingerprint: str
    scope: Literal["course", "unit"]
    unit_key: str | None = None
    standard_id: str
    decision: Literal["accept", "reject", "needs_review"]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


@router.post("/{run_id}/reviews")
def review(run_id: int, body: Review):
    with pool.connection() as conn:
        record = conn.execute("SELECT source_fingerprint, payload FROM evidence_run WHERE id=%s FOR UPDATE", (run_id,)).fetchone()
        if not record:
            raise HTTPException(404, "Evidence run not found")
        if record["source_fingerprint"] != body.source_fingerprint:
            raise HTTPException(409, "Review refers to different source evidence")
        coverage = record["payload"]["state"].get("coverage") or {}
        if body.scope == "unit":
            outcomes = coverage.get("units", {}).get(body.unit_key, {}).get("outcomes", {})
        else:
            if body.unit_key is not None:
                raise HTTPException(422, "Course review must not specify a unit")
            outcomes = coverage.get("course", {})
        if body.standard_id not in outcomes:
            raise HTTPException(422, "No computed outcome for this review target")
        row = conn.execute("""INSERT INTO evidence_review
            (evidence_run_id, scope, unit_key, standard_identifier, decision, actor, reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (run_id, body.scope, body.unit_key, body.standard_id, body.decision, body.actor, body.reason)).fetchone()
        return {"id": row["id"], "status": "recorded", "published": False}
