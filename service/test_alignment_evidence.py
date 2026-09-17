#!/usr/bin/env python3
"""Regression cases for evidence integrity and honest course aggregation.

Uses synthetic curriculum only. No network, database, API key, or paid calls.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from service.app.alignment_evidence import data, judge, requirements, sources, verify
from service import compare_standards

STANDARD = {"id": 1, "set_id": 1, "identifier": "DEMO.A", "statement": "Compare designs and test solutions.",
            "concept": "Design", "hierarchy_role": "leaf", "boundary_provenance": "drafted",
            "boundary_includes": [], "boundary_excludes": [], "nearest_csta": []}
SPECS = [{"standard_id": "DEMO.A", "statement": STANDARD["statement"],
          "requirements": [{"requirement_id": "R1", "quote": "Compare designs and "},
                           {"requirement_id": "R2", "quote": "test solutions."}],
          "interpretation_status": "drafted"}]


def lesson(name="demo::one", optional=False):
    return {"id": 1, "snapshot_id": 1, "unit_id": 1, "stable_id": name,
            "lesson_name": "Synthetic comparison task", "content_hash": "fixture",
            "absolute_position": 1, "has_lesson_plan": True,
            "plan": {"objectives": ["Compare designs and test solutions."],
                     "standards": [{"shortcode": "DO-NOT-LEAK"}],
                     "activities": [{"sections": [{"description_md": "Compare your designs and explain the tradeoffs.",
                        "tips": [{"type": "assessmentOpportunity", "markdown": "Check explanations for justified tradeoffs and evidence from tests."}]}]}]},
            "levels": [{"level_name": "design", "level_type": "Panels",
                        "student_text": "Test both solutions and record their results independently.",
                        "context": {"is_choice_option": optional, "choice_parent": "choice" if optional else None}}]}


def finding(rid="R1", quote="Compare your designs and explain the tradeoffs.",
            source="/plan/activities/0/sections/0/description_md", support="full", depth="supported_practice"):
    return {"requirement_id": rid, "support": support, "depth": depth,
            "rationale": "The explicit task supports this requirement.",
            "citations": [{"source_id": source, "quote": quote, "purpose": "task"}] if support != "none" else []}


def answer(first=None, second=None, boundary=False):
    return {"verdicts": [{"standard_id": "DEMO.A", "boundary_issue": boundary,
                         "boundary_reason": "The drafted note adds a restriction." if boundary else "",
                         "findings": [first or finding(), second or finding("R2", support="none")]}]}


class EvidenceTests(unittest.TestCase):
    def test_lossless_sources_and_no_inherited_alignment_tags(self):
        raw = lesson()
        raw["levels"][0]["student_text"] = "x" * 1000 + "Test the solution at the end."
        record = sources.extract(raw)
        self.assertIn("Test the solution at the end.", record["sources"][-1]["text"])
        self.assertNotIn("DO-NOT-LEAK", json.dumps(record))
        self.assertTrue(any(s["role"] == "assessment_criteria" for s in record["sources"]))

    def test_missing_resources_and_optional_readings_are_explicit(self):
        raw = lesson(optional=True)
        raw["plan"]["resources"] = [{"name": "Guide", "url": "https://example.invalid/guide"}]
        record = sources.extract(raw)
        self.assertEqual(record["sources"][-1]["pathway"], "choice")
        self.assertEqual(record["gaps"][0]["kind"], "linked_resource_not_in_snapshot")

    def test_no_plan_does_not_drop_student_task(self):
        raw = lesson()
        raw["plan"] = None
        raw["has_lesson_plan"] = False
        record = sources.extract(raw)
        self.assertEqual(len(record["sources"]), 1)
        self.assertEqual(record["gaps"], [])

    def test_requirements_cannot_omit_scope_or_invent_quotes(self):
        requirements.validate(SPECS, [STANDARD])
        bad = copy.deepcopy(SPECS)
        bad[0]["requirements"].pop()
        with self.assertRaises(ValueError):
            requirements.validate(bad, [STANDARD])
        bad = copy.deepcopy(SPECS)
        bad[0]["requirements"][0]["quote"] = "Design a robot"
        with self.assertRaises(ValueError):
            requirements.validate(bad, [STANDARD])

    def test_fabricated_quote_and_objective_do_not_prove_performance(self):
        record = sources.extract(lesson())
        for f in (finding(quote="Students create a complete operating system."),
                  finding(quote=STANDARD["statement"], source="/plan/objectives/0")):
            checked = verify.verify(answer(first=f), SPECS, record)
            self.assertEqual(checked[0]["findings"][0]["verification"], "invalid")
            result = verify.aggregate(SPECS, [record], {record["stable_id"]: checked})
            self.assertEqual(result["DEMO.A"]["coverage"], "none_observed")
            self.assertEqual(result["DEMO.A"]["evidence_sufficiency"], "incomplete")

    def test_missing_duplicate_and_invented_candidates_fail_closed(self):
        record = sources.extract(lesson())
        bads = [{"verdicts": []}, {"verdicts": answer()["verdicts"] * 2}, answer()]
        bads[-1]["verdicts"][0]["standard_id"] = "OTHER"
        for bad in bads:
            with self.assertRaises(ValueError):
                verify.verify(bad, SPECS, record)

    def test_missing_requirement_is_not_a_silent_negative(self):
        bad = answer()
        bad["verdicts"][0]["findings"].pop()
        with self.assertRaises(ValueError):
            verify.verify(bad, SPECS, sources.extract(lesson()))

    def test_complementary_required_performances_roll_up_across_lessons(self):
        one, two = sources.extract(lesson()), sources.extract(lesson("demo::two"))
        first = verify.verify(answer(), SPECS, one)
        second = verify.verify(answer(first=finding(support="none"),
                                      second=finding("R2", "Test both solutions and record their results independently.",
                                                     "/levels/0/student_text")), SPECS, two)
        result = verify.aggregate(SPECS, [one, two], {one["stable_id"]: first, two["stable_id"]: second})
        self.assertEqual(result["DEMO.A"]["coverage"], "full")
        self.assertFalse(result["DEMO.A"]["assessed_at_expected_demand"])

    def test_repetition_of_partial_work_never_becomes_full(self):
        one, two = sources.extract(lesson()), sources.extract(lesson("demo::two"))
        checked = verify.verify(answer(first=finding(support="partial")), SPECS, one)
        result = verify.aggregate(SPECS, [one, two], {one["stable_id"]: checked, two["stable_id"]: checked})
        self.assertEqual(result["DEMO.A"]["coverage"], "partial")
        self.assertEqual(result["DEMO.A"]["full_requirements"], [])

    def test_choice_depth_is_preserved_without_shared_coverage(self):
        record = sources.extract(lesson(optional=True))
        second = finding("R2", "Test both solutions and record their results independently.",
                         "/levels/0/student_text", depth="independent_performance")
        checked = verify.verify(answer(first=finding(support="none"), second=second), SPECS, record)
        self.assertEqual(checked[0]["findings"][1]["depth"], "independent_performance")
        result = verify.aggregate(SPECS, [record], {record["stable_id"]: checked})
        self.assertEqual(result["DEMO.A"]["coverage"], "none_observed")
        self.assertEqual(result["DEMO.A"]["conditional_requirements"], ["R2"])

    def test_shared_leadin_cannot_launder_optional_evidence(self):
        record = sources.extract(lesson(optional=True))
        mixed = finding()
        mixed["citations"].append({"source_id": "/levels/0/student_text", "purpose": "task",
                                   "quote": "Test both solutions and record their results independently."})
        checked = verify.verify(answer(first=mixed), SPECS, record)
        self.assertFalse(checked[0]["findings"][0]["shared_pathway"])

    def test_boundary_issue_coexists_with_positive_coverage(self):
        record = sources.extract(lesson())
        checked = verify.verify(answer(boundary=True), SPECS, record)
        outcome = verify.aggregate(SPECS, [record], {record["stable_id"]: checked})["DEMO.A"]
        self.assertEqual(outcome["coverage"], "partial")
        self.assertEqual(len(outcome["boundary_issues"]), 1)

    def test_failed_lessons_are_unknown_not_curricular_misses(self):
        record = sources.extract(lesson())
        outcome = verify.aggregate(SPECS, [record], {})["DEMO.A"]
        self.assertEqual(outcome["evidence_sufficiency"], "incomplete")
        self.assertEqual(outcome["unprocessed_lessons"], 1)

    def test_exposure_cannot_become_performance_through_label(self):
        record = sources.extract(lesson())
        checked = verify.verify(answer(first=finding(depth="exposure")), SPECS, record)
        self.assertEqual(checked[0]["findings"][0]["verification"], "invalid")

    def test_assessment_requires_cited_criteria_and_independent_task(self):
        record = sources.extract(lesson())
        f = finding(depth="independent_performance")
        checked = verify.verify(answer(first=f), SPECS, record)
        self.assertFalse(checked[0]["findings"][0]["assessed_at_expected_demand"])
        f["citations"].append({"source_id": "/plan/activities/0/sections/0/tips/0/markdown",
                               "purpose": "assessment", "quote": "Check explanations for justified tradeoffs and evidence from tests."})
        checked = verify.verify(answer(first=f), SPECS, record)
        self.assertTrue(checked[0]["findings"][0]["assessed_at_expected_demand"])

    def test_fingerprint_changes_when_source_or_requirement_changes(self):
        raw = lesson()
        before = sources.extract(raw)["evidence_sha256"]
        raw["levels"][0]["student_text"] += " An extra task."
        self.assertNotEqual(before, sources.extract(raw)["evidence_sha256"])

    def test_end_to_end_audit_live_stub_and_replay(self):
        dataset = {t: [] for t in data.TABLES}
        dataset.update({"run": [{"id": 1, "set_id": 1, "course_id": 1, "snapshot_id": 1, "scope_note": "Demo"}],
                        "course": [{"id": 1, "course_name": "Demo course", "snapshot_id": 99}],
                        "course_unit": [{"course_id": 1, "unit_id": 1, "position": 1}],
                        "unit": [{"id": 1, "snapshot_id": 1, "script_name": "demo", "unit_name": "Demo"}],
                        "snapshot": [{"id": 1, "source_commit": "demo-commit"}],
                        "standards_set": [{"id": 1, "title": "Demo standards"}],
                        "standard": [STANDARD], "lesson": [lesson()],
                        "standard_outcome": [{"run_id": 1, "standard_id": 1, "in_scope": True, "outcome": "developed"}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dataset.json").write_text(json.dumps(dataset))
            (root / "requirements.json").write_text(json.dumps(SPECS))
            base = ["--dataset", str(root / "dataset.json"), "--baseline-run", "1"]
            self.assertEqual(compare_standards.main(base + ["--out", str(root / "audit")]), 0)
            audit = json.loads((root / "audit/comparison.json").read_text())
            self.assertEqual(audit["outcomes"], {})
            self.assertEqual(audit["manifest"]["snapshot_id"], 1)  # run, not current course
            self.assertIn("not run", (root / "audit/comparison.html").read_text())
            captured = []

            def create(**kwargs):
                captured.append(kwargs)
                return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(answer()))],
                                       stop_reason="end_turn", usage=SimpleNamespace(input_tokens=10, output_tokens=20))

            stub = SimpleNamespace(Anthropic=lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
            with patch.dict(sys.modules, {"anthropic": stub}), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "synthetic-test-only"}):
                result = compare_standards.main(base + ["--out", str(root / "live"), "--live", "--model", "stub",
                                                       "--requirements", str(root / "requirements.json")])
            self.assertEqual(result, 0)
            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0]["system"][1]["cache_control"], {"type": "ephemeral"})
            self.assertNotIn("DO-NOT-LEAK", json.dumps(captured))
            replay_args = base + ["--out", str(root / "replay"), "--replay", str(root / "live/answers.json"),
                                  "--requirements", str(root / "requirements.json")]
            self.assertEqual(compare_standards.main(replay_args), 0)
            live = json.loads((root / "live/comparison.json").read_text())
            replay = json.loads((root / "replay/comparison.json").read_text())
            self.assertEqual(live["outcomes"], replay["outcomes"])
            dataset["lesson"][0]["levels"][0]["student_text"] += " Changed."
            (root / "dataset.json").write_text(json.dumps(dataset))
            replay_args[replay_args.index(str(root / "replay"))] = str(root / "bad-replay")
            with self.assertRaises(ValueError):
                compare_standards.main(replay_args)


if __name__ == "__main__":
    unittest.main()
