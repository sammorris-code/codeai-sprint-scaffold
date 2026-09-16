#!/usr/bin/env python3
"""Tests the alignment engine with the model call stubbed.

    python3 service/test_alignment.py

No key, no network, no database. The judgement a model makes is not testable
here and no unit test can check it — that is what the verification pass and the
human review queue are for. What IS testable is everything around it, and that
is where a wrong claim would come from:

  - the candidate set, and the grade-band comparison that builds it
  - each of the seven verification checks, including the ones that demote
  - the aggregate outcome, including the standards nothing claimed
  - the count check that has to balance

The stub returns claims designed to trip each check. If a check stops firing,
a claim that should have been demoted or dropped reaches a district instead.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from service.app.alignment import engine, verify                  # noqa: E402

failures, passes = [], 0


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"  ok    {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


LESSON = {"stable_id": "u::L1", "lesson_name": "A Lesson", "unit_name": "A Unit",
          "script_name": "u", "relative_position": 1, "lesson_group_name": "Content",
          "plan": {"objectives": ["Write a conditional."], "overview_md": "x"}}

DISTILLED = {
    "every_student": [
        {"action": "writes Python", "level": "lvl-1", "level_type": "pythonlab",
         "steps": ["Write a function that returns the total."]}],
    "one_option_only": [
        {"action": "draws or diagrams", "level": "lvl-2a",
         "level_type": "sketchlab", "choice_parent": "lvl-2"}],
    "produces": [], "checked": [], "authorship": {},
    "is_alternate_progression": False,
}


def main():
    print("\nGrade bands are compared by the grades they cover")
    check("a range expands", engine.grades_in("9-10") == {9, 10},
          f"{engine.grades_in('9-10')}")
    check("a wider range expands", engine.grades_in("9-12") == {9, 10, 11, 12})
    check("state and CSTA bands overlap",
          bool(engine.grades_in("9-10") & engine.grades_in("9-12")),
          "comparing the labels as strings would match nothing")
    check("a single grade works", engine.grades_in("6") == {6})
    check("an empty band is empty", engine.grades_in(None) == set())

    print("\nThe candidate set")
    standards = [
        {"identifier": "A", "grade_band": "9-10", "statement": "s", "concept": "c"},
        {"identifier": "B", "grade_band": "6-8", "statement": "s", "concept": "c"},
        {"identifier": "C", "grade_band": None, "statement": "s", "concept": "c"},
    ]
    kept, note = engine.candidate_standards(standards, None)
    check("with no grades given, nothing is filtered",
          len(kept) == 3 and note["filtered"] is False,
          "the skill says the default candidate set is the whole framework")
    kept, note = engine.candidate_standards(standards, "9-12")
    ids = {s["identifier"] for s in kept}
    check("a band that does not overlap is dropped", "B" not in ids, f"{ids}")
    check("a band with no grades is kept", "C" in ids, f"{ids}")

    print("\nVerification: evidence must point at a student task")
    kept, dropped = verify.verify_lesson(
        [{"standard_id": "A", "level": "developed",
          "evidence": "The lesson is about algorithms.",
          "cognitive_verb_match": True, "artifact_match": True,
          "is_choice_level": False, "choice_option": None, "note": None}],
        [], ["A"], LESSON, DISTILLED)
    check("'the lesson is about X' is not evidence",
          not kept and dropped and dropped[0]["kind"] == "no_evidence",
          f"{kept} {dropped}")

    kept, _ = verify.verify_lesson(
        [{"standard_id": "A", "level": "developed",
          "evidence": "Level 3 has students write a function that totals a list.",
          "cognitive_verb_match": True, "artifact_match": True,
          "is_choice_level": False, "choice_option": None, "note": None}],
        [], ["A"], LESSON, DISTILLED)
    check("a named task is evidence", len(kept) == 1, f"{kept}")

    print("\nVerification: the cognitive verb is a ceiling")
    kept, _ = verify.verify_lesson(
        [{"standard_id": "A", "level": "mastered",
          "evidence": "Level 3 has students answer a multiple-choice question.",
          "cognitive_verb_match": False, "artifact_match": True,
          "is_choice_level": False, "choice_option": None, "note": None}],
        [], ["A"], LESSON, DISTILLED)
    check("a task below the verb is demoted",
          kept[0]["level"] == "developed" and kept[0]["proposed_level"] == "mastered",
          f"{kept[0]['level']}")
    check("and the demotion is flagged",
          any(f["kind"] == "depth_doubt" for f in kept[0]["flags"]))

    print("\nVerification: a choice branch is met by a fraction of the class")
    kept, _ = verify.verify_lesson(
        [{"standard_id": "A", "level": "mastered",
          "evidence": "Students build the scenario they chose in level 2a.",
          "cognitive_verb_match": True, "artifact_match": True,
          "is_choice_level": True, "choice_option": "lvl-2a", "note": None}],
        [], ["A"], LESSON, DISTILLED)
    check("a choice claim is capped at introduced",
          kept[0]["level"] == "introduced", f"{kept[0]['level']}")
    check("the option is kept on the record",
          kept[0]["choice_option"] == "lvl-2a")

    print("\nVerification: artifact mismatch is kept with a caveat, never silently")
    kept, _ = verify.verify_lesson(
        [{"standard_id": "A", "level": "developed",
          "evidence": "Students make a poster about sorting.",
          "cognitive_verb_match": True, "artifact_match": False,
          "is_choice_level": False, "choice_option": None,
          "note": "the standard names a program"}],
        [], ["A"], LESSON, DISTILLED)
    check("the claim survives", len(kept) == 1)
    check("with an artifact flag",
          any(f["kind"] == "artifact_mismatch" for f in kept[0]["flags"]))

    print("\nVerification: a standard outside the candidate set cannot be claimed")
    kept, dropped = verify.verify_lesson(
        [{"standard_id": "ZZ", "level": "developed",
          "evidence": "Level 3 has students write a function.",
          "cognitive_verb_match": True, "artifact_match": True,
          "is_choice_level": False, "choice_option": None, "note": None}],
        [], ["A"], LESSON, DISTILLED)
    check("an invented standard is rejected",
          not kept and dropped[0]["kind"] == "not_a_candidate", f"{dropped}")

    print("\nVerification: the overclaim scan")
    many = [{"standard_id": f"S{i}", "level": "introduced",
             "evidence": f"Level {i} has students do a specific task number {i}.",
             "cognitive_verb_match": True, "artifact_match": True,
             "is_choice_level": False, "choice_option": None, "note": None}
            for i in range(6)]
    kept, _ = verify.verify_lesson(many, [], [f"S{i}" for i in range(6)],
                                   LESSON, DISTILLED)
    check("six claims on one lesson flags them all",
          len(kept) == 6 and all(
              any(f["kind"] == "overclaim" for f in c["flags"]) for c in kept))
    kept, _ = verify.verify_lesson(many[:3], [], [f"S{i}" for i in range(6)],
                                   LESSON, DISTILLED)
    check("three does not",
          not any(f["kind"] == "overclaim" for c in kept for f in c["flags"]))

    print("\nVerification: shared evidence is annotated, not dropped")
    shared = [{"standard_id": i, "level": "developed",
               "evidence": "Students write the reflection in level 7.",
               "cognitive_verb_match": True, "artifact_match": True,
               "is_choice_level": False, "choice_option": None, "note": None}
              for i in ("A", "B")]
    kept, _ = verify.verify_lesson(shared, [], ["A", "B"], LESSON, DISTILLED)
    check("both claims are kept — many-to-many is how crosscutting works",
          len(kept) == 2)
    check("and each names the other",
          all("overlaps" in (c["note"] or "") for c in kept),
          f"{[c['note'] for c in kept]}")

    print("\nThe aggregate outcome, including the misses")
    claims = {"u::L1": [{"standard_id": "A", "level": "introduced"}],
              "u::L2": [{"standard_id": "A", "level": "developed"}]}
    rejections = {"u::L1": [{"standard_id": "B", "kind": "boundary_exclusion",
                             "reason": "excluded"}],
                  "u::L2": []}
    outcomes = verify.aggregate(claims, rejections, ["A", "B", "C"])
    check("the best level across lessons wins",
          outcomes["A"]["outcome"] == "developed", f"{outcomes['A']}")
    check("a boundary rejection is its own outcome",
          outcomes["B"]["outcome"] == "boundary_issue", f"{outcomes['B']}")
    check("a standard nothing touched is not_addressed",
          outcomes["C"]["outcome"] == "not_addressed", f"{outcomes['C']}")
    check("every candidate gets a row — this is what a CSV cannot do",
          len(outcomes) == 3)

    result = verify.count_check(outcomes, ["A", "B", "C"])
    check("the count check balances", result["balances"], f"{result}")
    cover = verify.coverage(outcomes)
    check("coverage counts only the rated levels",
          cover["addressed"] == 1 and cover["percent"] == 33, f"{cover}")

    print("\nThe prompt")
    block = engine.standards_block([
        {"identifier": "A", "statement": "Do a thing.", "concept": "Algorithms",
         "boundary_includes": ["student writes it"],
         "boundary_excludes": ["a poster"], "keywords": ["thing"],
         "boundary_provenance": "drafted"}])
    check("boundaries reach the prompt",
          "student writes it" in block and "a poster" in block)
    check("an unreviewed boundary says so in the prompt",
          "no person has checked them" in block)
    lesson_text = engine.lesson_block(LESSON, DISTILLED)
    check("the student actions reach the prompt",
          "writes Python" in lesson_text)
    check("the choice branch is separated in the prompt",
          "only some students do" in lesson_text.lower())
    check("keywords are marked as insufficient",
          "never sufficient evidence" in block)

    print("\nThe model call, stubbed")

    class StubMessages:
        def create(self, **kwargs):
            self.kwargs = kwargs
            class Block:
                type = "text"
                text = ('{"claims":[{"standard_id":"A","level":"developed",'
                        '"evidence":"Level 3 has students write a function.",'
                        '"cognitive_verb_match":true,"artifact_match":true,'
                        '"is_choice_level":false,"choice_option":null,'
                        '"note":null}],"considered_and_rejected":[]}')
            class Usage:
                input_tokens = 100
                output_tokens = 50
                cache_creation_input_tokens = 0
                cache_read_input_tokens = 900
            class Response:
                content = [Block()]
                usage = Usage()
            return Response()

    class StubClient:
        def __init__(self):
            self.messages = StubMessages()

    client = StubClient()
    usage = {}
    answer = engine.judge(client, "STANDARDS TEXT", LESSON, DISTILLED,
                          usage=usage)
    check("the answer parses", answer["claims"][0]["standard_id"] == "A")
    sent = client.messages.kwargs
    check("the standards are cached, the lesson is not",
          sent["system"][1].get("cache_control") == {"type": "ephemeral"}
          and "cache_control" not in str(sent["messages"]),
          "the lesson must sit after the breakpoint or every call re-writes "
          "the cache")
    check("the answer shape is constrained",
          sent["output_config"]["format"]["type"] == "json_schema")
    check("usage is accumulated", usage["calls"] == 1
          and usage["cache_read_input_tokens"] == 900)
    spend = engine.cost_of(usage, "claude-opus-5")
    check("cost is computed from real prices", 0 < spend < 0.01, f"${spend}")

    print(f"\n{passes} checks passed, {len(failures)} failed")
    if failures:
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nNot covered: whether a judgement is correct. No unit test can "
          "check that.\nThat is what the verification pass and the review "
          "queue are for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
