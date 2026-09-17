"""Check source integrity; retain semantic judgments as proposed, never proven."""
from collections import Counter

from .judge import DEPTHS, SUPPORT


def verify(answer, specs, evidence):
    verdicts = answer.get("verdicts", [])
    expected = {s["standard_id"]: s for s in specs}
    counts = Counter(v.get("standard_id") for v in verdicts)
    if set(counts) != set(expected) or any(n != 1 for n in counts.values()):
        raise ValueError("Model must return every candidate exactly once, including rejections.")
    sources = {s["source_id"]: s for s in evidence["sources"]}
    result = []
    for verdict in verdicts:
        spec = expected[verdict["standard_id"]]
        findings = verdict.get("findings", [])
        ids = Counter(f.get("requirement_id") for f in findings)
        if set(ids) != {r["requirement_id"] for r in spec["requirements"]} or any(n != 1 for n in ids.values()):
            raise ValueError("Model must return every requirement exactly once.")
        verified = []
        for finding in findings:
            errors, citations = [], []
            support, depth = finding.get("support"), finding.get("depth")
            if support not in SUPPORT or depth not in DEPTHS:
                errors.append("invalid_rating")
            if not (finding.get("rationale") or "").strip():
                errors.append("missing_rationale")
            for citation in finding.get("citations", []):
                source = sources.get(citation.get("source_id"))
                quote = citation.get("quote") or ""
                purpose = citation.get("purpose")
                if not source or len(quote.strip()) < 12 or quote not in source["text"]:
                    errors.append("unverifiable_quote")
                    continue
                if purpose not in {"task", "assessment"}:
                    errors.append("invalid_citation_purpose")
                    continue
                if source["role"] in {"intended_objective", "intended_context"}:
                    errors.append("intent_is_not_instructional_evidence")
                    continue
                citations.append({**citation, "pathway": source["pathway"],
                                  "choice_parent": source["choice_parent"],
                                  "text_sha256": source["text_sha256"]})
            tasks = [c for c in citations if c["purpose"] == "task"]
            if support != "none" and not tasks:
                errors.append("no_task_or_exposure_citation")
            if support == "none" and citations:
                errors.append("rejection_has_positive_citations")
            if support in {"exposure", "prerequisite"} and depth != "exposure":
                errors.append("support_and_depth_conflict")
            if support in {"full", "partial"} and depth == "exposure":
                errors.append("exposure_does_not_establish_performance")
            # Requiring every task citation to be shared prevents a shared lead-in
            # from laundering a performance found only in an optional profile.
            shared = bool(tasks) and all(c["pathway"] == "shared" for c in tasks)
            assessment = (support == "full" and depth == "independent_performance"
                          and any(c["purpose"] == "assessment" and
                                  c["pathway"] == "shared" for c in citations) and shared)
            verified.append({**finding, "citations": citations,
                             "verification": "invalid" if errors else "source_verified",
                             "verification_errors": sorted(set(errors)),
                             "shared_pathway": shared,
                             "assessed_at_expected_demand": assessment and not errors})
        result.append({**verdict, "findings": verified, "review_status": "proposed"})
    return result


def aggregate(specs, lessons, results):
    """Union fully supported requirements, never add partial ratings into full."""
    expected_lessons = {l["stable_id"] for l in lessons}
    if set(results) - expected_lessons:
        raise ValueError("Results contain lessons outside this course snapshot.")
    unprocessed = sorted(expected_lessons - set(results))
    evidence_gaps = sum(bool(l["gaps"]) for l in lessons)
    resource_gaps = sum(any(g["kind"] == "linked_resource_not_in_snapshot" for g in l["gaps"])
                        for l in lessons)
    outcomes = {}
    for spec in specs:
        sid = spec["standard_id"]
        required = {r["requirement_id"] for r in spec["requirements"]}
        full, partial, assessed, conditional = set(), set(), set(), set()
        depths, refs, issues = [], [], []
        exposures = []
        invalid = 0
        for lesson_id, verdicts in results.items():
            for verdict in verdicts:
                if verdict["standard_id"] != sid:
                    continue
                if verdict.get("boundary_issue"):
                    issues.append({"lesson": lesson_id, "reason": verdict.get("boundary_reason")})
                for finding in verdict["findings"]:
                    rid = finding["requirement_id"]
                    if finding["verification"] != "source_verified":
                        invalid += 1
                        continue
                    support = finding["support"]
                    if support in {"exposure", "prerequisite"}:
                        exposures.append({"lesson": lesson_id, "requirement": rid, "support": support})
                    if support not in {"full", "partial"}:
                        continue
                    refs.append({"lesson": lesson_id, "requirement": rid,
                                 "support": support, "shared": finding["shared_pathway"]})
                    if not finding["shared_pathway"]:
                        conditional.add(rid)
                        continue
                    depths.append(finding["depth"])
                    (full if support == "full" else partial).add(rid)
                    if finding["assessed_at_expected_demand"]:
                        assessed.add(rid)
        coverage = "full" if full == required else "partial" if full or partial else "none_observed"
        outcomes[sid] = {
            "coverage": coverage,
            "instructional_depth": max(depths, key=DEPTHS.index) if depths else
                "exposure" if exposures else "none_observed",
            "assessed_at_expected_demand": assessed == required,
            "full_requirements": sorted(full), "partial_requirements": sorted(partial - full),
            "unsupported_requirements": sorted(required - full - partial),
            "not_fully_supported_requirements": sorted(required - full),
            "conditional_requirements": sorted(conditional), "exposures": exposures,
            "evidence_sufficiency": "incomplete" if unprocessed or evidence_gaps or invalid else "available_snapshot_complete",
            "unprocessed_lessons": len(unprocessed), "lessons_with_resource_gaps": resource_gaps,
            "lessons_with_evidence_gaps": evidence_gaps,
            "invalid_findings": invalid, "boundary_issues": issues,
            "review_status": "proposed", "evidence_refs": refs,
        }
    if set(outcomes) != {s["standard_id"] for s in specs}:
        raise AssertionError("Outcome identities do not match candidate identities.")
    return outcomes
