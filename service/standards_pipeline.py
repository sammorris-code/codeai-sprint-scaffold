#!/usr/bin/env python3
"""Lesson -> unit -> course standards workflow. Default: prepare inputs, no API spend."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.app.alignment_evidence import data
from service.app.alignment_evidence.sources import digest
from service.app.standards_v2 import inventory, pathways, pipeline, presentation


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", help="Typed local export; otherwise read DATABASE_URL")
    ap.add_argument("--baseline-run", type=int)
    ap.add_argument("--human-run", type=int, help="Comparison only; never sent to model stages")
    ap.add_argument("--corpus", type=Path, help="Extracted corpus for standalone inventory stage")
    ap.add_argument("--stage", choices=["all", "inventory", "performances"], default="all")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=Path("runs/standards-v2-cache"))
    ap.add_argument("--model", help="Explicit model ID; used in all cache keys")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay-cache", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--lesson", action="append")
    ap.add_argument("--pathways", type=Path, help="Explicit lesson-route groups for course alternatives")
    ap.add_argument("--performances", type=Path, help="Previously prepared required-performance interpretations")
    ap.add_argument("--max-failures", type=int, default=3)
    ap.add_argument("--persist", action="store_true", help="Save a proposed v2 run to DATABASE_URL after migration")
    args = ap.parse_args(argv)
    if (args.limit is not None and args.limit < 1) or args.max_failures < 1:
        ap.error("Limits must be positive")
    if args.out.exists() and any(args.out.iterdir()):
        ap.error("Use a fresh output directory to preserve prior evidence")
    if args.corpus:
        if args.stage != "inventory" or args.baseline_run or args.human_run or args.persist:
            ap.error("--corpus supports standalone --stage inventory without baseline/persistence")
        lessons = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((args.corpus / "lessons").glob("*/*.json"))]
        if not lessons:
            ap.error("Corpus has no lessons/*/*.json files")
        selected = {"lessons": lessons, "standards": [], "baseline_claims": [],
                    "baseline_outcomes": [], "scope_origin": "standalone_inventory",
                    "course": {"course_name": "Corpus inventory"}, "snapshot": {}, "run": {},
                    "standards_set": {}}
        dataset = None
    else:
        if args.baseline_run is None:
            ap.error("--baseline-run is required")
        dataset = data.load(args.dataset, os.environ.get("DATABASE_URL"))
        selected = data.select(dataset, args.baseline_run)
        lessons = selected["lessons"]
    if len({l["stable_id"] for l in lessons}) != len(lessons):
        ap.error("Duplicate lesson identity in snapshot")
    human = []
    if args.human_run:
        other = data.select(dataset, args.human_run)
        if any(other["run"][k] != selected["run"][k] for k in ("set_id", "course_id", "snapshot_id")):
            ap.error("Human comparison must refer to the same course, standard set and snapshot")
        human = other["baseline_claims"]
    config = json.loads(args.pathways.read_text()) if args.pathways else None
    routes = pathways.context(lessons, config)
    evidence = [inventory.prepare(l, routes) for l in lessons]
    chosen = [e["stable_id"] for e in evidence]
    if args.lesson:
        if set(args.lesson) - set(chosen):
            ap.error("Unknown lesson stable ID")
        chosen = [lid for lid in chosen if lid in args.lesson]
    if args.limit:
        chosen = chosen[:args.limit]
    specs = json.loads(args.performances.read_text()) if args.performances else None
    client = None
    if args.live or args.replay_cache:
        if not args.model:
            ap.error("--live and --replay-cache require --model for reproducible stage keys")
    if args.live:
        from service.app.alignment.engine import load_key
        if not load_key():
            ap.error("No ANTHROPIC_API_KEY configured; input preparation needs no key")
        import anthropic
        client = anthropic.Anthropic()
    args.out.mkdir(parents=True, exist_ok=True)
    calls = pipeline.Calls(client, args.model, args.cache, args.live,
                           args.out / "usage.json", args.max_failures)
    state = {"inventories": {}, "unit_summaries": {}, "specs": specs,
             "discovery": {}, "lesson_results": {}, "unit_results": {}, "failures": {}}
    if args.live or args.replay_cache:
        state = pipeline.run(evidence, selected["standards"], routes, calls, chosen, specs, args.stage,
                             lambda s: pipeline.write(args.out / "checkpoint.json", s))
    pipeline_files = Path(__file__).parent / "app" / "standards_v2"
    fingerprint = digest({p.name: p.read_text() for p in sorted(pipeline_files.glob("*.py"))})
    manifest = {"pipeline": pipeline.VERSION, "pipeline_sha256": fingerprint,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "mode": "live" if args.live else "cache_replay" if args.replay_cache else "prepared_only",
                "stage": args.stage, "model": args.model, "baseline_run_id": args.baseline_run,
                "human_run_id": args.human_run, "course_name": selected["course"]["course_name"],
                "snapshot": selected["snapshot"], "standard_set": selected["standards_set"],
                "scope_origin": selected["scope_origin"], "scope_note": selected["run"].get("scope_note"),
                "selected_lessons": chosen, "expected_lesson_count": len(evidence),
                "input_sha256": digest({"evidence": evidence, "standards": selected["standards"], "pathways": config}),
                "review_status": "proposed", "usage": calls.usage, "cost_usd": None,
                "pathway_warnings": routes["warnings"]}
    document = {"manifest": manifest, "state": state, "sources": evidence,
                "domains": routes["domains"], "standards": selected["standards"],
                "baseline_claims": selected["baseline_claims"], "baseline_outcomes": selected["baseline_outcomes"],
                "human_claims": human}
    document["comparison"] = presentation.compare(document)
    pipeline.write(args.out / "report.json", document)
    pipeline.write(args.out / "inventory.json", state["inventories"])
    pipeline.write(args.out / "performances.json", state["specs"])
    pipeline.write(args.out / "sources.json", evidence)
    (args.out / "report.html").write_text(presentation.html(document), encoding="utf-8")
    if args.persist:
        from service.app.standards_v2.store import save
        saved_id = save(document, os.environ.get("DATABASE_URL"))
        pipeline.write(args.out / "store-receipt.json", {"evidence_run_id": saved_id})
        print(f"Saved proposed evidence run {saved_id}")
    print(json.dumps({"mode": manifest["mode"], "lessons": len(evidence),
                      "units": len({e["unit_key"] for e in evidence}),
                      "synthesized_inventories": len(state["inventories"]),
                      "unit_summaries": len(state["unit_summaries"]),
                      "failures": len(state["failures"]), "usage": calls.usage,
                      "report": str(args.out / "report.html")}, indent=2))
    return 1 if state["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
