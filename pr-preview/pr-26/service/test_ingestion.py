#!/usr/bin/env python3
"""Tests ingestion end to end, with the model call stubbed out.

Everything about ingestion is deterministic except drafting the boundaries, so
everything except that is tested here for real: the document is parsed, the
statements are extracted word for word, the count is reconciled, the rows are
written, the headings are linked, and the review gate flips the set to
publishable only when every boundary has a verdict.

The one stubbed part is the call to Claude. Stubbing it keeps this test free
and offline, and it is honest about what is NOT covered: the quality of a
drafted boundary is a judgement, and no unit test can check it. That is what
the human review gate is for.

    python3 service/test_ingestion.py
"""
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from service.app.ingestion import boundaries as boundaries_module
from service.app.ingestion.boundaries import CstaAnalog, DraftedBoundary
from service.app.ingestion import analogs as analog_gate

CSV = pathlib.Path(__file__).parent / "sample_documents" / "DEMO_CS_2026.csv"

failures, passes = [], 0


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"  ok    {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def fake_draft(standards, progress=None, include_specialty=False,
               usage=None, gate=None):
    """Stands in for Claude. Returns a boundary shaped like a real one for
    every standard that is not a heading.

    The signature has to track the real one. It did not once - the real
    function grew a `usage` argument and this did not - and every ingest test
    failed with an unexpected-keyword error that looked like a service bug.
    """
    if gate is not None:
        gate.update({"dropped": 0, "reasons": {}, "examples": []})
    if usage is not None:
        drafting = [s for s in standards if s.hierarchy_role != "umbrella"]
        usage.update({"calls": 1, "input_tokens": 400 * len(drafting),
                      "output_tokens": 650 * len(drafting),
                      "cache_creation_input_tokens": 10500,
                      "cache_read_input_tokens": 0})
    return {
        s.identifier: DraftedBoundary(
            identifier=s.identifier,
            boundary_includes=[f"Students do what {s.identifier} describes and "
                               f"produce something a teacher can look at."],
            boundary_excludes=["A mention with no student work.",
                               "A word match with no task behind it."],
            keywords=["demo", s.concept.lower()],
            analogs=[],
            unclear=None,
        )
        for s in standards if s.hierarchy_role != "umbrella"
    }


# Keep the real one: a test below exercises its batch-splitting, and the stub
# would quietly stand in for it and pass without testing anything.
real_draft_boundaries = boundaries_module.draft_boundaries
boundaries_module.draft_boundaries = fake_draft
import service.app.main as main
main.draft_boundaries = fake_draft

from fastapi.testclient import TestClient

with TestClient(main.app) as c:
    # Start from a known state for this framework only.
    main.execute("""DELETE FROM standards_set
                    WHERE framework = 'DEMO' AND standard_set = 'CS-INGEST-TEST'""")

    form = {"framework": "DEMO", "standard_set": "CS-INGEST-TEST",
            "set_type": "standards", "framework_year": "2026",
            "title": "Demo ingestion test", "claimed_count": "14"}

    print("Characterize")
    with open(CSV, "rb") as f:
        r = c.post("/api/standards-sets/characterize",
                   files={"file": ("DEMO_CS_2026.csv", f, "text/csv")},
                   data={"claimed_count": "14"})
    check("returns 200", r.status_code == 200, r.text[:120])
    rep = r.json()
    check("finds 14 standards", rep["extracted_count"] == 14)
    check("reconciles the count", rep["count_reconciled"] is True)
    check("spots the heading row", rep["umbrella_count"] == 1)
    check("estimates the spend first", rep["cost_to_draft_boundaries"]["estimated_usd"] > 0)
    before = main.one("SELECT count(*) AS n FROM standards_set")["n"]

    print("\nIngest")
    with open(CSV, "rb") as f:
        r = c.post("/api/standards-sets",
                   files={"file": ("DEMO_CS_2026.csv", f, "text/csv")}, data=form)
    check("returns 201", r.status_code == 201, r.text[:160])
    r_ingest = r
    set_id = r.json()["id"]
    check("the set is not publishable yet", r.json()["publishable"] is False)
    check("its boundaries are marked drafted",
          r.json()["boundary_provenance"] == "drafted")
    check("the response reports what the run actually cost",
          r.json()["cost"] and r.json()["cost"]["usd"] > 0,
          f"got {r.json().get('cost')}")
    check("and says it is measured rather than estimated",
          "Measured" in r.json()["cost"]["note"])
    check("characterize wrote nothing; ingest wrote one set",
          main.one("SELECT count(*) AS n FROM standards_set")["n"] == before + 1)

    print("\nWhat landed in the store")
    std = main.rows("SELECT * FROM standard WHERE set_id = %(s)s ORDER BY id",
                    {"s": set_id})
    check("14 standards written", len(std) == 14)
    verbatim = CSV.read_text(encoding="utf-8-sig").splitlines()[1].split(",")[1]
    check("the statement is word for word", std[0]["statement"] == verbatim,
          f"{std[0]['statement']!r} vs {verbatim!r}")
    umbrella = [s for s in std if s["hierarchy_role"] == "umbrella"]
    check("the heading is marked umbrella", len(umbrella) == 1)
    check("the heading is rated by rollup", umbrella[0]["rating_rule"] == "rollup")
    children = [s for s in std if s["parent_id"] == umbrella[0]["id"]]
    check("its two standards point at it", len(children) == 2,
          f"found {len(children)}")
    check("every standard has an inclusion",
          all(s["boundary_includes"] for s in std))
    check("every standard has an exclusion",
          all(s["boundary_excludes"] for s in std))
    sourced = [s for s in std if s["boundary_provenance"] == "source"]
    check("provenance comes from the document", len(sourced) == 3,
          f"3 rows carry clarifying text, found {len(sourced)}")

    print("\nA document that states no total")
    # Real state frameworks usually do not state their own count. That must not
    # block ingestion, but it must not report a green check either.
    from service.app.ingestion.characterize import characterize_csv
    unstated = characterize_csv(CSV.read_bytes())
    check("count_reconciled is None, not True", unstated.count_reconciled is None,
          f"got {unstated.count_reconciled!r} - a green light for a check that "
          f"never ran is worse than no light")
    check("and it says so", any("not reconciled against anything" in w
                               for w in unstated.warnings))

    print("\nA stray identifier is named, not buried in a shape count")
    # Two rows here carry an OCR artefact: L1 mistyped as LI. The point of the
    # scheme line is to name those, not to report "3 shapes present".
    strays = characterize_csv(
        b"Code,Standard,Strand\n"
        b"L1.CS.D.01,A standard.,Computing Systems\n"
        b"L1.NI.CY.01,Another standard.,Networks\n"
        b"L2.AP.PD.01,A third.,Programming\n"
        b"LI.CS.T.01,An OCR artefact.,Computing Systems\n"
        b"Li.CA.CVT.01,Another artefact.,Impacts\n")
    scheme = strays.identifier_scheme
    check("both strays are named", "LI.CS.T.01" in scheme and "Li.CA.CVT.01" in scheme,
          scheme[:100])
    check("the majority pattern is stated", "AN.A.A.N" in scheme, scheme[:100])
    check("it says they are copied verbatim", "verbatim" in scheme)

    print("\nThe CSTA reference")
    from service.app.ingestion import csta
    from pydantic import ValidationError

    check("a 9-12 framework gets CSTA's high-school standards",
          len(csta.reference_for(["9-10", "11-12"])) == 46,
          f"got {len(csta.reference_for(['9-10', '11-12']))}")
    check("bands are matched by overlap, not by string equality",
          bool(csta.grades_in("9-12") & csta.grades_in("9-10")),
          "'9-12' and '9-10' must overlap, or the reference is never sent")
    check("a middle-grades framework gets different standards",
          csta.reference_for(["6-8"]) != csta.reference_for(["9-10"]))
    check("unknown bands fall back to everything, never to nothing",
          len(csta.reference_for([])) == 196,
          "sending nothing silently returns the tool to guessing")
    ref = csta.reference_for(["9-12"])
    check("the reference carries CSTA's own boundary language",
          "Counts:" in csta.as_prompt(ref))
    check("every id in it is real", all(s["id"] in csta.valid_ids(ref) for s in ref))
    check("an invented id is not in the valid set",
          "HS-TOTALLY-MADE-UP-99" not in csta.valid_ids(ref))

    print("\nBoundaries need at least one inclusion and two exclusions")
    def boundary(includes, excludes):
        return DraftedBoundary(identifier="X", boundary_includes=includes,
                               boundary_excludes=excludes, keywords=["k"])
    try:
        boundary(["a"], ["x"])
        check("a single exclusion is refused", False, "one was accepted")
    except ValidationError:
        check("a single exclusion is refused", True)
    try:
        boundary(["a", "b", "c"], ["v", "w", "x", "y", "z", "z2"])
        check("three includes and six excludes are allowed", True)
    except ValidationError as e:
        check("three includes and six excludes are allowed", False, str(e)[:80])

    print("\nThe analog rate is reported")
    # The honest answer is often "no analog". Reporting the rate is how you
    # notice the drafter stretching to fill the field on every row.
    rate = r_ingest.json()["nearest_csta"]
    check("the response reports how many had no analog", "no_analog" in rate)
    check("with_analog and no_analog account for every drafted standard",
          rate["with_analog"] + rate["no_analog"] == 13,
          f"got {rate['with_analog']} + {rate['no_analog']}, expected 13 "
          f"(14 standards less the umbrella heading)")
    check("the note warns that a high rate is stretching",
          "stretching" in rate["note"])
    check("the response reports what the analog gate rejected",
          "rejected" in rate and "dropped" in rate["rejected"],
          "a gate set too strict looks identical to a drafter that stopped "
          "stretching unless the drops are reported")

    print("\nBounds are a sanity check, not the style rule")
    # An earlier version capped inclusions at three. A standard came back with
    # four - which is not wrong - and the hard cap took its whole batch, and
    # then the whole run, down with it. A schema cannot judge redundancy.
    try:
        boundary(["a", "b", "c", "d"], ["x", "y"])
        check("a fourth inclusion is accepted", True)
    except ValidationError as e:
        check("a fourth inclusion is accepted", False,
              "four facets is a judgement call, not a schema error")
    try:
        boundary(["a"] * 7, ["x", "y"])
        check("seven inclusions is still refused as runaway", False)
    except ValidationError:
        check("seven inclusions is still refused as runaway", True)

    print("\nWhat a run costs is measured, not estimated")
    import types as _t
    from service.app.ingestion import boundaries as _B

    class _Std:
        hierarchy_role = "standard"; grade_band = "9-12"; clarification = None
        def __init__(self, i):
            self.identifier = f"C-{i}"; self.statement = f"Statement {i}."
            self.concept = "X"

    class _Usage:
        def __init__(self, **kw): [setattr(self, k, v) for k, v in kw.items()]

    class _Fake:
        seen = []
        class messages:
            @staticmethod
            def parse(**kw):
                ids = [l.split(": ")[1] for l in kw["messages"][0]["content"].splitlines()
                       if l.startswith("Identifier: ")]
                first = not _Fake.seen
                _Fake.seen.append(1)
                return _t.SimpleNamespace(
                    parsed_output=_B.DraftedBatch(boundaries=[
                        _B.DraftedBoundary(identifier=i, boundary_includes=["a"],
                                           boundary_excludes=["x", "y"],
                                           keywords=["k"]) for i in ids]),
                    usage=_Usage(input_tokens=400 * len(ids),
                                 output_tokens=650 * len(ids),
                                 cache_creation_input_tokens=10500 if first else 0,
                                 cache_read_input_tokens=0 if first else 10500))

    _real = _B._client
    _B._client = lambda: _Fake()
    try:
        spend = {}
        real_draft_boundaries([_Std(i) for i in range(1, 21)], usage=spend)
    finally:
        _B._client = _real

    check("usage is accumulated across every call", spend["calls"] == 2,
          f"got {spend['calls']}")
    check("output tokens are totalled", spend["output_tokens"] == 650 * 20,
          f"got {spend['output_tokens']}")
    check("the cache write is counted once",
          spend["cache_creation_input_tokens"] == 10500,
          f"got {spend['cache_creation_input_tokens']}")
    check("cache reads are counted separately",
          spend["cache_read_input_tokens"] == 10500,
          f"got {spend['cache_read_input_tokens']}")

    cost = _B.actual_cost(spend)
    check("a dollar figure comes back", cost["usd"] > 0, str(cost["usd"]))
    check("it says it is measured rather than estimated",
          "Measured" in cost["note"])
    # Cache reads must be charged at the cache rate, not the input rate, or the
    # figure is wrong in the same direction the old estimate was.
    naive = (spend["input_tokens"] + spend["cache_read_input_tokens"]
             + spend["cache_creation_input_tokens"]) / 1e6 * 5.0 \
            + spend["output_tokens"] / 1e6 * 25.0
    check("cache reads are not charged at the full input rate",
          cost["usd"] < naive, f"{cost['usd']} should be under {naive:.4f}")

    print("\nOne bad standard does not lose its batch")
    import types, pydantic as _pyd
    from service.app.ingestion import boundaries as B

    class Std:
        hierarchy_role = "standard"; grade_band = "9-12"; clarification = None
        def __init__(self, i):
            self.identifier = f"T-{i}"; self.statement = f"Statement {i}."
            self.concept = "X"

    seen = []

    class Fake:
        class messages:
            @staticmethod
            def parse(**kw):
                ids = [l.split(": ")[1] for l in kw["messages"][0]["content"].splitlines()
                       if l.startswith("Identifier: ")]
                seen.append(len(ids))
                if "T-4" in ids:
                    raise _pyd.ValidationError.from_exception_data("DraftedBatch", [])
                return types.SimpleNamespace(usage=None, parsed_output=B.DraftedBatch(
                    boundaries=[B.DraftedBoundary(identifier=i, boundary_includes=["a"],
                                                  boundary_excludes=["x", "y"],
                                                  keywords=["k"]) for i in ids]))

    real_client = B._client
    B._client = lambda: Fake()
    try:
        # real_draft_boundaries, not B.draft_boundaries: that name now points at
        # the stub, which would pass this test without running any of the code
        # it claims to test.
        real_draft_boundaries([Std(i) for i in range(1, 11)])
        check("the run fails when a standard cannot be drafted", False, "it did not")
    except B.BoundaryRefused as e:
        check("the run fails when a standard cannot be drafted", True)
        check("and names the one at fault, not the whole batch",
              e.identifier == "T-4", f"named {e.identifier}")
        check("having split down to a single standard", 1 in seen,
              f"batch sizes tried: {seen}")
        check("the other nine were drafted on the way", len(seen) > 2,
              f"only {len(seen)} call(s) - no splitting happened")
    finally:
        B._client = real_client

    print("\nThe same set cannot be ingested twice")
    with open(CSV, "rb") as f:
        r = c.post("/api/standards-sets",
                   files={"file": ("DEMO_CS_2026.csv", f, "text/csv")}, data=form)
    check("returns 409", r.status_code == 409, f"got {r.status_code}")
    check("names the existing set",
          str(set_id) in r.json()["detail"]["error"]["message"])

    print("\nThe review gate")
    q = c.get(f"/api/standards-sets/{set_id}/boundary-queue").json()
    check("every standard awaits a verdict", q["remaining"] == 14, str(q["remaining"]))
    check("the set reports itself unpublishable", q["set"]["publishable"] is False)

    r = c.get("/api/standards-sets").json()
    this = [s for s in r["items"] if s["id"] == set_id][0]
    check("and so does the registry", this["publishable"] is False)

    ids = [i["standard_id"] for i in q["items"]]
    for n, sid in enumerate(ids[:-1], 1):
        c.post(f"/api/standards/{sid}/boundary-verdict",
               json={"verdict": "accept", "actor": "test@example.invalid"})
    mid = c.get(f"/api/standards-sets/{set_id}/boundary-queue").json()
    check("13 checked leaves 1 remaining", mid["remaining"] == 1, str(mid["remaining"]))
    check("the set is still not publishable", mid["set"]["publishable"] is False,
          "one unchecked boundary must hold the whole set back")

    r = c.post(f"/api/standards/{ids[-1]}/boundary-verdict",
               json={"verdict": "edit",
                     "edited_includes": ["A reviewer rewrote this one."],
                     "actor": "test@example.invalid", "reason": "too narrow"})
    check("the last verdict flips the set", r.json()["set_now_publishable"] is True,
          r.text[:120])
    final = c.get(f"/api/standards-sets/{set_id}/boundary-queue").json()
    check("nothing remains", final["remaining"] == 0)
    check("the set is publishable", final["set"]["publishable"] is True)
    check("its provenance reads drafted+reviewed",
          final["set"]["boundary_provenance"] == "drafted+reviewed")

    edited = main.one("SELECT boundary_includes FROM standard WHERE id = %(i)s",
                      {"i": ids[-1]})
    check("the reviewer's edit was kept",
          edited["boundary_includes"] == ["A reviewer rewrote this one."])
    events = main.one("""SELECT count(*) AS n FROM review_event
                         WHERE standard_id = ANY(%(ids)s)""", {"ids": ids})
    check("every verdict is recorded", events["n"] == 14, str(events["n"]))

    print("\nAn edit verdict with nothing edited")
    r = c.post(f"/api/standards/{ids[0]}/boundary-verdict",
               json={"verdict": "edit", "actor": "test@example.invalid"})
    check("is refused", r.status_code == 422, f"got {r.status_code}")

    main.execute("DELETE FROM standards_set WHERE id = %(i)s", {"i": set_id})

print("\nThe analog gate checks the evidence, not the claim")
# A bare identifier is an assertion and nothing can test an assertion. On a real
# 55-standard run, 80% of standards came back with an analog against a prompt
# saying most have none. So the drafter now quotes the CSTA span it adapted,
# and these are the checks that quote has to survive.
CSTA_TEXT = ("Decompose a problem into smaller parts to design a modular "
             "program. Counts: breaking a task into named procedures.")


def gated(adapted, includes=None, csta_text=CSTA_TEXT):
    """Run one claimed analog through the gate. Returns the reason it was
    dropped, or None when it was kept."""
    b = DraftedBoundary(
        identifier="OK-1",
        boundary_includes=includes or
            ["learners decompose a problem into smaller parts before coding"],
        boundary_excludes=["naming steps without writing any", "watching a demo"],
        keywords=["decompose"],
        analogs=[CstaAnalog(identifier="X-1", adapted=adapted)])
    dropped = analog_gate.apply_gate(b, {"X-1": csta_text})
    return dropped[0][1] if dropped else None


check("a span quoted from the standard and carried into the boundary is kept",
      gated("decompose a problem into smaller parts") is None)

check("a span that is not in the CSTA standard it credits is dropped",
      gated("evaluate a design against its specification") is not None,
      "this is the check that cannot be gamed by quoting the boundary back")

check("a span that left no trace in the boundary is dropped",
      gated("breaking a task into named procedures",
            includes=["learners name three sorting algorithms"]) is not None,
      "wording that was adapted shows up in the wording")

check("a one-word span is too short to prove anything",
      gated("abstraction") is not None,
      "a single term is a substring of half the reference")

check("punctuation and case do not decide the check",
      gated("Decompose a problem, into smaller parts.") is None,
      "quotes drift by a comma; that is not evidence of anything")

check("the identifiers survive the gate as a plain list of strings",
      DraftedBoundary(identifier="OK-2", boundary_includes=["a"],
                      boundary_excludes=["b", "c"], keywords=["d"],
                      analogs=[CstaAnalog(identifier="X-1", adapted="q")]
                      ).nearest_csta == ["X-1"],
      "the database column stays text[]; nothing downstream changes")

check("a reference with no text for the standard keeps the analog",
      gated("decompose a problem into smaller parts", csta_text=None) is None,
      "a gap in our own files must not be charged to the drafter")

print()
print(f"{passes} passed, {len(failures)} failed")
if failures:
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("Ingestion works end to end. The drafted boundaries themselves are a\n"
      "judgement no test can check - that is what the review gate is for.")
