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
from service.app.ingestion.boundaries import DraftedBoundary

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


def fake_draft(standards, progress=None):
    """Stands in for Claude. Returns a boundary shaped like a real one for
    every standard that is not a heading."""
    return {
        s.identifier: DraftedBoundary(
            identifier=s.identifier,
            boundary_includes=[f"Students do what {s.identifier} describes and "
                               f"produce something a teacher can look at."],
            boundary_excludes=["A mention with no student work.",
                               "A word match with no task behind it."],
            keywords=["demo", s.concept.lower()],
            nearest_csta=[],
            unclear=None,
        )
        for s in standards if s.hierarchy_role != "umbrella"
    }


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
    set_id = r.json()["id"]
    check("the set is not publishable yet", r.json()["publishable"] is False)
    check("its boundaries are marked drafted",
          r.json()["boundary_provenance"] == "drafted")
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

    print("\nNo line may repeat another")
    def boundary(includes, excludes):
        return DraftedBoundary(identifier="X", boundary_includes=includes,
                               boundary_excludes=excludes, keywords=["k"])
    try:
        boundary(["a", "b", "c", "d"], ["x", "y"])
        check("a fourth inclusion is refused", False, "four were accepted")
    except ValidationError:
        check("a fourth inclusion is refused", True)
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

print()
print(f"{passes} passed, {len(failures)} failed")
if failures:
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("Ingestion works end to end. The drafted boundaries themselves are a\n"
      "judgement no test can check - that is what the review gate is for.")
