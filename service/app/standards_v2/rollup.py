"""Deterministic lesson -> unit -> course aggregation of qualified evidence."""
from .pathways import universal, compatible


def summarize(specs, verdicts, domains, complete):
    outcomes = {}
    for spec in specs:
        sid = spec["standard_id"]
        related = [v for v in verdicts if v["standard_id"] == sid]
        requirements = {}
        refs, integrated = set(), []
        for verdict in related:
            integrated += [c["conditions"] for c in verdict["integration_clauses"]]
        for req in spec["requirements"]:
            full, partial, exposure, prerequisites, assessed = [], [], [], [], []
            for verdict in related:
                for finding in verdict["findings"]:
                    if finding["requirement_id"] != req["requirement_id"]:
                        continue
                    target = {"full": full, "partial": partial, "exposure": exposure,
                              "prerequisite": prerequisites}.get(finding["support"])
                    if target is not None:
                        target.extend(c["conditions"] for c in finding["clauses"])
                    assessed.extend(c["conditions"] for c in finding["assessment_clauses"])
                    for clause in finding["clauses"]:
                        refs.update(clause["item_ids"])
            requirements[req["requirement_id"]] = {
                "full_on_all_paths": universal(full, domains),
                "performance_on_all_paths": universal(full + partial, domains),
                "assessment_on_all_paths": universal(assessed, domains),
                "full_clauses": full, "partial_clauses": partial,
                "exposure_clauses": exposure, "prerequisite_clauses": prerequisites,
                "assessment_clauses": assessed,
            }
        full_components = all(r["full_on_all_paths"] is True for r in requirements.values())
        integration_ok = not spec["integration_required"] or universal(integrated, domains) is True
        has_performance = any(r["full_clauses"] or r["partial_clauses"] for r in requirements.values())
        shared_performance = any(r["performance_on_all_paths"] is True for r in requirements.values())
        has_exposure = any(r["exposure_clauses"] for r in requirements.values())
        has_prerequisite = any(r["prerequisite_clauses"] for r in requirements.values())
        coverage = ("full" if full_components and integration_ok else "components_only" if full_components
                    else "partial" if shared_performance else "conditional" if has_performance
                    else "exposure_only" if has_exposure else "supporting_only" if has_prerequisite
                    else "none_observed" if complete else "unknown")
        formula = [r["full_clauses"] for r in requirements.values()]
        if spec["integration_required"]:
            formula.append(integrated)
        assessments_full = all(r["assessment_on_all_paths"] is True for r in requirements.values())
        conflicts = []
        for rid in requirements:
            positive_units = {v.get("unit_key") for v in related if v["stage"] == "lesson" and any(f["requirement_id"] == rid and f["support"] != "none" for f in v["findings"])}
            rejected_units = {v.get("unit_key") for v in related if v["stage"] == "unit" and any(f["requirement_id"] == rid and f["support"] == "none" for f in v["findings"])}
            if positive_units & rejected_units:
                conflicts.append(rid)
        outcomes[sid] = {"coverage": coverage, "requirements": requirements,
                         "integrated_performance_on_all_paths": integration_ok,
                         "full_on_at_least_one_compatible_path": compatible(formula),
                         "assessed_at_expected_demand": coverage == "full" and assessments_full,
                         "evidence_sufficiency": "available_snapshot_complete" if complete else "incomplete",
                         "evidence_item_ids": sorted(refs), "review_status": "proposed",
                         "boundary_issues": [v["boundary_issue"] for v in related if v["boundary_issue"]],
                         "cross_pass_disagreements": conflicts}
    return outcomes


def build(specs, expected_evidence, inventories, lesson_results, unit_results, domains):
    units = {}
    for evidence in expected_evidence:
        key = evidence["unit_key"]
        units.setdefault(key, {"unit_name": evidence["unit_name"], "position": evidence["unit_position"],
                               "lessons": []})["lessons"].append(evidence["stable_id"])
    course_verdicts, course_complete = [], True
    for key, unit in units.items():
        local = [v for lid in unit["lessons"] for v in lesson_results.get(lid, [])]
        reviewed = unit_results.get(key, [])
        all_spec_ids = {s["standard_id"] for s in specs}
        # All-standard second pass is mandatory before a negative course conclusion.
        complete = (all(lid in inventories for lid in unit["lessons"])
                    and {v["standard_id"] for v in reviewed} == all_spec_ids
                    and not any(inventories[lid].get("uncertainties") or
                                any(d["disposition"] == "unclear" for d in inventories[lid].get("source_dispositions", []))
                                for lid in unit["lessons"] if lid in inventories)
                    and not any(e["gaps"] for e in expected_evidence if e["unit_key"] == key))
        unit["outcomes"] = summarize(specs, local + reviewed, domains, complete)
        unit["reviewed_standard_count"] = len({v["standard_id"] for v in reviewed})
        unit["inventory_lesson_count"] = sum(lid in inventories for lid in unit["lessons"])
        course_verdicts.extend(local + reviewed)
        course_complete &= complete
    return {"units": units, "course": summarize(specs, course_verdicts, domains, course_complete)}
