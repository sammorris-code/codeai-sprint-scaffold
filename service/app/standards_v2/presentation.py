"""One review surface for saved artifacts and the internal API workbench."""
import json
from pathlib import Path


def compare(document):
    ids = {s["id"]: s["identifier"] for s in document["standards"]}
    def pairs(records):
        return {(r["lesson_stable_id"], ids[r["standard_id"]]) for r in records if r["standard_id"] in ids}
    baseline, human = pairs(document["baseline_claims"]), pairs(document["human_claims"])
    proposed = set()
    items = {i["item_id"]: i for inv in document["state"]["inventories"].values() for i in inv["items"]}
    for source in ("lesson_results", "unit_results"):
        for verdicts in document["state"][source].values():
            for verdict in verdicts:
                for finding in verdict["findings"]:
                    if finding["support"] != "none":
                        for group in finding["evidence_sets"]:
                            for item in group:
                                proposed.add((items[item]["lesson_id"], verdict["standard_id"]))
    return {"baseline_pairs": len(baseline), "human_pairs": len(human),
            "baseline_human_overlap": len(baseline & human),
            "proposed_pairs": len(proposed) if document["state"].get("coverage") else None,
            "proposed_human_overlap": len(proposed & human) if document["state"].get("coverage") else None,
            "human_only_vs_proposed": sorted(human - proposed) if document["state"].get("coverage") else [],
            "proposed_only_vs_human": sorted(proposed - human),
            "note": "Pair agreement only, not accuracy. Human ratings may be imported placeholders. Pilots are incomplete."}


def html(document):
    root = Path(__file__).resolve().parents[3] / "tools" / "standards-mapper"
    if not root.exists():
        root = Path(__file__).resolve().parents[3] / "site" / "tools" / "standards-mapper"
    script = (root.resolve() / "evidence.js").read_text()
    style = (root.resolve() / "evidence.css").read_text()
    payload = json.dumps(document, ensure_ascii=False, default=str).replace("<", "\\u003c")
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Lesson, unit and course alignment</title><style>' + style + '</style>'
            '<main><h1>Lesson, unit and course alignment</h1><div id="report"></div></main>'
            '<script id="report-data" type="application/json">' + payload + '</script>'
            '<script>' + script + '</script></html>')
