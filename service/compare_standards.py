#!/usr/bin/env python3
"""Opt-in comparison against a stored baseline; reads the database, writes files only.

No API call unless --live is supplied. Default mode audits sources and preserves
the baseline, with new alignment explicitly marked not run. See the companion
standards-evidence-comparison.md for the rating rules and review limitations.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.app.alignment_evidence import data, judge, report, requirements, sources, verify


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", help="Local JSON export of database tables; otherwise DATABASE_URL")
    parser.add_argument("--list-runs", action="store_true")
    parser.add_argument("--export-dataset", help="Write a read-only database export for offline use")
    parser.add_argument("--baseline-run", type=int)
    parser.add_argument("--out", type=Path, help="New output directory (normally runs/<name>)")
    parser.add_argument("--limit", type=int, help="Pilot on the first N lessons; remaining lessons stay unknown")
    parser.add_argument("--lesson", action="append", help="Exact stable ID; repeat to select a controlled pilot")
    parser.add_argument("--requirements", type=Path, help="Reuse source-grounded requirements.json")
    parser.add_argument("--whole-statements", action="store_true", help="Skip model decomposition; one requirement per standard")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Call the configured model")
    mode.add_argument("--replay", type=Path, help="Verify saved answers against exactly matching inputs; no API calls")
    parser.add_argument("--model", help="Explicit model ID for live calls; no guessed default")
    parser.add_argument("--max-failures", type=int, default=3,
                        help="Stop paid calls after this many failed lessons (default: 3)")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.max_failures < 1:
        parser.error("--max-failures must be positive")
    dataset = data.load(args.dataset, os.environ.get("DATABASE_URL"))
    if args.export_dataset:
        write_json(Path(args.export_dataset), dataset)
    if args.list_runs:
        for run in dataset["run"]:
            print(f'{run["id"]}: course={run["course_id"]} set={run["set_id"]} snapshot={run["snapshot_id"]} {run["scope_note"]}')
        return 0
    if args.baseline_run is None or args.out is None:
        parser.error("--baseline-run and --out are required unless --list-runs is used")
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("Output directory must be empty; prior comparison evidence is never overwritten")
    selected = data.select(dataset, args.baseline_run)
    standards, lessons = selected["standards"], selected["lessons"]
    evidence = [sources.extract(l) for l in lessons]
    evidence_by_id = {e["stable_id"]: e for e in evidence}
    if len(evidence_by_id) != len(evidence):
        raise ValueError("Duplicate lesson stable IDs in the selected snapshot")
    subset = evidence
    if args.lesson:
        unknown = set(args.lesson) - set(evidence_by_id)
        if unknown:
            parser.error(f"Unknown lessons: {sorted(unknown)}")
        subset = [e for e in evidence if e["stable_id"] in args.lesson]
    if args.limit:
        subset = subset[:args.limit]

    usage, client = {}, None
    if args.live:
        if not args.model:
            parser.error("--live requires an explicit --model")
        from service.app.alignment.engine import load_key
        if not load_key():
            parser.error("No ANTHROPIC_API_KEY configured; audit and replay require no key")
        import anthropic
        client = anthropic.Anthropic()
    args.out.mkdir(parents=True, exist_ok=True)
    specs = requirements.whole_statements(standards)
    if args.requirements:
        specs = json.loads(args.requirements.read_text(encoding="utf-8"))
    elif args.replay:
        parser.error("--replay requires the original --requirements file")
    elif args.live and not args.whole_statements:
        specs = []
        for start in range(0, len(standards), 10):
            batch = standards[start:start + 10]
            try:
                answer = judge.call(client, args.model, requirements.DRAFT_RULES,
                                    "Use state statements only.",
                                    [{"standard_id": s["identifier"], "statement": s["statement"]} for s in batch],
                                    requirements.DRAFT_SCHEMA, usage)
            finally:
                write_json(args.out / "usage.json", usage)
            drafted = answer["standards"]
            for spec in drafted:
                spec["interpretation_status"] = "drafted"
            requirements.validate(drafted, batch)
            specs.extend(drafted)
            write_json(args.out / "requirements.partial.json", specs)
            write_json(args.out / "usage.json", usage)
            print(f"Requirements prepared: {len(specs)}/{len(standards)}", flush=True)
    requirements_sha = requirements.validate(specs, standards)
    write_json(args.out / "requirements.json", specs)
    advisory = [{"standard_id": s["identifier"], "boundary_provenance": s.get("boundary_provenance"),
                 "boundary_includes": s.get("boundary_includes"), "boundary_excludes": s.get("boundary_excludes"),
                 "csta_reference_ids": s.get("nearest_csta") or [],
                 "authority": "advisory_interpretation_not_state_requirements"} for s in standards]
    prefix = {"requirements": specs, "advisory_boundaries": advisory}
    module_dir = Path(__file__).parent / "app" / "alignment_evidence"
    pipeline_files = {p.name: p.read_text() for p in sorted(module_dir.glob("*.py"))}
    pipeline_files["compare_standards.py"] = Path(__file__).read_text()
    pipeline_sha = sources.digest(pipeline_files)
    input_sha = sources.digest({"prefix": prefix, "evidence": evidence,
                               "snapshot": selected["snapshot"], "pipeline_sha256": pipeline_sha})
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                           cwd=Path(__file__).parent, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    manifest = {
        "pipeline": "standards-evidence-v1", "pipeline_sha256": pipeline_sha,
        "code_revision": revision, "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "replay" if args.replay else "audit_only",
        "baseline_run_id": args.baseline_run, "baseline_sha256": sources.digest(selected["baseline_claims"]),
        "course_name": selected["course"]["course_name"],
        "standards_title": selected["standards_set"]["title"],
        "standards_set": selected["standards_set"], "scope_note": selected["run"]["scope_note"],
        "scope_origin": selected["scope_origin"], "snapshot_id": selected["run"]["snapshot_id"],
        "source_commit": selected["snapshot"]["source_commit"],
        "candidate_count": len(standards), "course_lesson_count": len(evidence),
        "selected_lessons": [e["stable_id"] for e in subset], "model": args.model,
        "requirements_sha256": requirements_sha, "input_sha256": input_sha,
        "review_status": "proposed", "cost_usd": None,
        "cost_note": "Token usage is measured; no unverified price table is used.",
    }
    write_json(args.out / "manifest.json", manifest)
    write_json(args.out / "evidence.json", evidence)
    replay = None
    if args.replay:
        replay = json.loads(args.replay.read_text(encoding="utf-8"))
        if replay.get("input_sha256") != input_sha:
            raise ValueError("Replay input fingerprint differs: sources, requirements, boundaries, or pipeline changed")
        if set(replay.get("answers", {})) - set(evidence_by_id):
            raise ValueError("Replay contains unknown lessons")
        manifest["model"] = replay.get("model")
        manifest["replay_source_usage"] = replay.get("usage", {})
        write_json(args.out / "manifest.json", manifest)
    results, answers, failures = {}, {}, {}
    for index, item in enumerate(subset, 1):
        if not args.live and not replay:
            break
        lid = item["stable_id"]
        try:
            if replay:
                if lid not in replay["answers"]:
                    continue
                answer = replay["answers"][lid]
            else:
                answer = judge.call(client, args.model, judge.RULES, prefix, item, judge.ANSWER_SCHEMA, usage)
            answers[lid] = answer
            results[lid] = verify.verify(answer, specs, item)
        except Exception as exc:
            # Failure is preserved and never becomes a negative curricular judgment.
            failures[lid] = f"{type(exc).__name__}: {exc}"
        write_json(args.out / "answers.json", {"input_sha256": input_sha, "model": args.model,
                                              "answers": answers, "failures": failures, "usage": usage})
        write_json(args.out / "usage.json", usage)
        print(f"Lessons processed: {index}/{len(subset)}; failures: {len(failures)}", flush=True)
        if args.live and len(failures) >= args.max_failures:
            print("Failure limit reached; remaining lessons stay unprocessed.", flush=True)
            break
    outcomes = verify.aggregate(specs, evidence, results) if args.live or args.replay else {}
    output = {"manifest": manifest, "audit": report.audit(lessons, evidence, selected["baseline_claims"]),
              "standards": standards, "requirements": specs,
              "baseline_outcomes": selected["baseline_outcomes"], "baseline_claims": selected["baseline_claims"],
              "results": results, "outcomes": outcomes, "failures": failures, "usage": usage}
    write_json(args.out / "comparison.json", output)
    (args.out / "comparison.html").write_text(report.render(output), encoding="utf-8")
    print(json.dumps(output["audit"], indent=2))
    print(f"Wrote {args.out / 'comparison.html'}. No database rows were modified.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
