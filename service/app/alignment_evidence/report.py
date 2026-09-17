"""An offline, escaped HTML comparison. No external assets or data requests."""
from collections import Counter
from html import escape


def audit(lessons, evidence, claims):
    return {
        "lessons": len(lessons),
        "baseline_claims": len(claims),
        "baseline_levels": dict(Counter(c["level"] for c in claims)),
        "baseline_flags": dict(Counter(f.get("kind", "unknown") for c in claims
                                       for f in c.get("flags") or [])),
        "lessons_without_plan": sum(not l.get("has_lesson_plan") for l in lessons),
        "sources": sum(len(e["sources"]) for e in evidence),
        "source_characters": sum(len(s["text"]) for e in evidence for s in e["sources"]),
        "conditional_sources": sum(s["pathway"] != "shared" for e in evidence for s in e["sources"]),
        "lessons_with_missing_linked_resources": sum(
            any(g["kind"] == "linked_resource_not_in_snapshot" for g in e["gaps"]) for e in evidence),
        "student_screens_over_legacy_900_character_cap": sum(
            len(l.get("student_text") or "") > 900 for lesson in lessons for l in lesson.get("levels") or []),
        "plan_sections_over_legacy_900_character_cap": sum(
            len(s.get("description_md") or "") > 900 for l in lessons
            for a in (l.get("plan") or {}).get("activities") or [] for s in a.get("sections") or []),
        "note": "Structural audit only. Existing prose claims have not been semantically rejudged.",
    }


def render(report):
    def h(value):
        return escape(str(value if value is not None else ""))

    manifest = report["manifest"]
    outcomes = report.get("outcomes") or {}
    sid_by_db = {s["id"]: s["identifier"] for s in report["standards"]}
    existing = {sid_by_db[o["standard_id"]]: o for o in report["baseline_outcomes"]
                if o["standard_id"] in sid_by_db}
    rows, details = [], []
    for i, standard in enumerate(report["standards"]):
        sid = standard["identifier"]
        outcome = outcomes.get(sid)
        old = existing.get(sid, {}).get("outcome", "not recorded")
        new = outcome["coverage"] if outcome else "not run"
        depth = outcome["instructional_depth"] if outcome else "—"
        sufficiency = outcome["evidence_sufficiency"] if outcome else "not evaluated"
        rows.append(f'<tr><th scope="row"><a href="#s{i}">{h(sid)}</a></th><td>{h(old)}</td>'
                    f'<td>{h(new)}</td><td>{h(depth)}</td><td>{h(sufficiency)}</td></tr>')
        content = [f'<details id="s{i}"><summary>{h(sid)} — {h(standard["statement"])}</summary>',
                   '<h3>Baseline claims (preserved)</h3>']
        claims = [c for c in report["baseline_claims"] if c["standard_id"] == standard["id"]]
        for claim in claims:
            content.append(f'<p><b>{h(claim["lesson_stable_id"])}</b> · {h(claim["level"])}'
                           f' · review: {h(claim.get("review_status"))}</p><blockquote>{h(claim["evidence"])}</blockquote>')
        if not claims:
            content.append('<p>No stored claims.</p>')
        content.append('<h3>Evidence pipeline</h3>')
        if not outcome:
            content.append('<p>Not run. No new alignment or coverage claim is being made.</p>')
        else:
            content.append(f'<p>Not fully supported requirements: {h(", ".join(outcome["not_fully_supported_requirements"])) or "none"}. '
                           f'Conditional requirements: {h(", ".join(outcome["conditional_requirements"])) or "none"}. '
                           f'Assessment at expected demand: {h(outcome["assessed_at_expected_demand"])}.</p>')
            for lesson_id, verdicts in report["results"].items():
                for verdict in verdicts:
                    if verdict["standard_id"] != sid:
                        continue
                    positive = any(f["support"] != "none" or f["verification_errors"] for f in verdict["findings"])
                    # Rejections remain inspectable without overwhelming the page.
                    content.append(f'<details><summary>{h(lesson_id)} — {"evidence / review" if positive else "no alignment"}</summary>')
                    if verdict.get("boundary_issue"):
                        content.append(f'<p>Boundary review: {h(verdict["boundary_reason"])}</p>')
                    for finding in verdict["findings"]:
                        content.append(f'<p><b>{h(finding["requirement_id"])}</b>: {h(finding["support"])} · '
                                       f'{h(finding["depth"])} · {h(finding["verification"])}<br>{h(finding["rationale"])}</p>')
                        for error in finding["verification_errors"]:
                            content.append(f'<p class="warning">{h(error)}</p>')
                        for citation in finding["citations"]:
                            content.append(f'<p><code>{h(citation["source_id"])}</code> · {h(citation["pathway"])}'
                                           f' · {h(citation["purpose"])}</p><blockquote>{h(citation["quote"])}</blockquote>')
                    content.append('</details>')
        content.append('</details>')
        details.append("\n".join(content))
    audit_items = "".join(f'<li>{h(k.replace("_", " "))}: {h(v)}</li>' for k, v in report["audit"].items()
                          if not isinstance(v, dict))
    failures = "".join(f'<li>{h(k)}: {h(v)}</li>' for k, v in report.get("failures", {}).items())
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Standards evidence comparison</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1150px;margin:32px auto;padding:0 24px;color:#17252d}}
h1,h2,h3{{line-height:1.2}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #ccd5db}}
thead{{background:#edf3f6}}.scroll{{overflow-x:auto}}details{{border:1px solid #ccd5db;border-radius:6px;padding:14px;margin:12px 0}}
summary{{cursor:pointer;font-weight:600}}blockquote{{white-space:pre-wrap;border-left:3px solid #527d8d;margin:12px 0;padding:8px 16px;overflow-wrap:anywhere}}
.warning{{background:#fff0d7;padding:12px}}code{{overflow-wrap:anywhere}}a{{color:#175c86}}:focus-visible{{outline:3px solid #175c86;outline-offset:3px}}</style>
<main><h1>Standards evidence comparison</h1>
<p>{h(manifest["course_name"])} · {h(manifest["standards_title"])} · baseline run {h(manifest["baseline_run_id"])}</p>
<p class="warning">Mode: {h(manifest["mode"])}. All new judgments are proposed. Source checks verify quotations, not educational validity.
Coverage and depth are separate; neither establishes student mastery. A pilot does not establish whole-course gaps.</p>
<p>Scope: {h(manifest["scope_note"])}. Candidate source: {h(manifest["scope_origin"])}.
Processed {len(report["results"])} of {manifest["course_lesson_count"]} course lessons.</p>
<p>Snapshot commit: <code>{h(manifest["source_commit"])}</code><br>
Input fingerprint: <code>{h(manifest["input_sha256"])}</code></p>
<h2>Source audit</h2><ul>{audit_items}</ul>
<h2>Course outcomes</h2><div class="scroll"><table><caption>Original outcomes and proposed evidence findings</caption>
<thead><tr><th scope="col">Standard</th><th scope="col">Baseline</th><th scope="col">Shared coverage</th>
<th scope="col">Highest supported depth</th><th scope="col">Evidence sufficiency</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<h2>Review evidence</h2>{"".join(details)}
<h2>Processing failures</h2><ul>{failures or "<li>None recorded.</li>"}</ul></main></html>'''
