"""Immutable v2 run artifacts and separate reviewer decisions; no auto-publishing."""
import json
from ..alignment_evidence.sources import digest


def save(document, dsn):
    if not dsn:
        raise ValueError("--persist requires DATABASE_URL")
    manifest = document["manifest"]
    if manifest.get("pipeline") != "lesson-unit-course-v2":
        raise ValueError("Not a v2 artifact")
    import psycopg
    with psycopg.connect(dsn) as conn:
        base = conn.execute("SELECT course_id, snapshot_id, set_id FROM run WHERE id=%s",
                            (manifest["baseline_run_id"],)).fetchone()
        if not base or base[1] != manifest["snapshot"]["id"] or base[2] != manifest["standard_set"]["id"]:
            raise ValueError("Persist target does not match artifact snapshot and standards")
        if manifest["scope_origin"] != "stored_outcomes":
            # Still save the artifact, but always proposed; scope fallback is visible.
            document["manifest"]["scope_needs_review"] = True
        raw = json.dumps(document, ensure_ascii=False, default=str)
        row = conn.execute("""INSERT INTO evidence_run
            (baseline_run_id, source_fingerprint, artifact_hash, payload)
            VALUES (%s,%s,%s,%s::jsonb)
            ON CONFLICT (artifact_hash) DO UPDATE SET artifact_hash=EXCLUDED.artifact_hash
            RETURNING id""", (manifest["baseline_run_id"], manifest["input_sha256"], digest(document), raw)).fetchone()
        for inv in document["state"]["inventories"].values():
            conn.execute("""INSERT INTO instructional_inventory
                (snapshot_id, lesson_stable_id, source_fingerprint, interpretation_hash, payload)
                VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT (interpretation_hash) DO NOTHING""",
                (base[1], inv["stable_id"], inv["evidence_sha256"], digest(inv), json.dumps(inv)))
        if document["state"]["specs"] is not None:
            specs = document["state"]["specs"]
            conn.execute("""INSERT INTO performance_interpretation
                (set_id, interpretation_hash, payload) VALUES (%s,%s,%s::jsonb)
                ON CONFLICT (interpretation_hash) DO NOTHING""", (base[2], digest(specs), json.dumps(specs)))
        return row[0]
