#!/usr/bin/env python3
"""Proves the API returns what the fixtures promise.

This is the test that makes the whole arrangement honest. The interface is
built against contract/fixtures/, then pointed at this service by changing one
block in loader.js. That swap is only safe if the two produce the same shapes.

So: load the fixtures into Postgres, ask the API, and compare. When they
disagree, one of them is wrong and somebody has to choose which.

    python3 service/test_contract.py            against a running service
    BASE=http://localhost:8000 python3 ...      somewhere else
"""
import json
import os
import pathlib
import sys

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))   # so `from service...` resolves when run directly
FIXTURES = ROOT / "contract" / "fixtures"
BASE = os.environ.get("BASE", "http://localhost:8000")

failures = []
passes = 0


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"  ok    {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def fx(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def strip(node):
    """Drop the _fixture_notes keys. They document the fixture; the API has no
    equivalent and should not."""
    if isinstance(node, dict):
        return {k: strip(v) for k, v in node.items() if not k.startswith("_")}
    if isinstance(node, list):
        return [strip(v) for v in node]
    return node


c = httpx.Client(base_url=BASE, timeout=20)


def reset():
    """Reload the fixtures before testing.

    This test changes data: it accepts a record, rejects another, and changes a
    level. Without a reset it passes once and fails on the second run, because
    the store now holds the decisions the first run made.

    CI never saw that, since CI always starts from an empty database. Somebody
    running it twice on their own machine would, and would reasonably conclude
    they had broken something. A test that only works once is a trap.
    """
    try:
        import psycopg
        from service.load_fixtures import load, DSN
        with psycopg.connect(DSN) as conn:
            outcomes, records = load(conn)
    except Exception as e:
        # Fatal, not a warning. A test that cannot establish its starting state
        # is not testing what it claims to. The first version of this printed a
        # note and carried on, and the note scrolled past while the failures it
        # caused looked like real regressions.
        sys.exit(f"Could not reset the fixtures, so this test cannot run:\n"
                 f"  {e}\n"
                 f"Point DATABASE_URL at the database the service is using.")
    print(f"Reset: {outcomes} outcomes, {records} records reloaded.\n")


reset()

print("Standards sets")
api = c.get("/api/standards-sets").json()
fixture = strip(fx("standards-sets"))
check("count matches", api["total"] == fixture["total"],
      f"api {api['total']} vs fixture {fixture['total']}")
for a, f in zip(api["items"], fixture["items"]):
    for key in ("framework", "standard_set", "set_type", "framework_year",
                "title", "standard_count", "boundary_provenance", "all_boundaries_checked"):
        check(f"{f['standard_set']}.{key}", a[key] == f[key],
              f"api {a[key]!r} vs fixture {f[key]!r}")

print("\nReview queue")
api = c.get("/api/runs/1/queue").json()
fixture = strip(fx("review-queue"))
check("14 standards returned", api["total"] == fixture["total"],
      f"api {api['total']} vs fixture {fixture['total']}")
check("standards with no evidence are kept",
      sum(1 for i in api["items"] if not i["records"]) ==
      sum(1 for i in fixture["items"] if not i["records"]),
      "a queue that drops them makes the totals wrong")

by_id = {i["standard"]["identifier"]: i for i in api["items"]}
for f in fixture["items"]:
    ident = f["standard"]["identifier"]
    a = by_id.get(ident)
    if not a:
        check(f"{ident} present", False, "missing from the API")
        continue
    check(f"{ident} outcome", a["outcome"]["outcome"] == f["outcome"]["outcome"],
          f"api {a['outcome']['outcome']!r} vs fixture {f['outcome']['outcome']!r}")
    check(f"{ident} in_scope", a["outcome"]["in_scope"] == f["outcome"]["in_scope"])
    check(f"{ident} record count", len(a["records"]) == len(f["records"]),
          f"api {len(a['records'])} vs fixture {len(f['records'])}")
    for ar, fr in zip(a["records"], f["records"]):
        for key in ("level", "evidence", "note", "authorship", "is_choice_level",
                    "choice_option", "review_status", "lesson_content_hash"):
            check(f"{ident} record {fr['id']}.{key}", ar[key] == fr[key],
                  f"api {ar[key]!r} vs fixture {fr[key]!r}")
        check(f"{ident} record {fr['id']}.flags", ar["flags"] == fr["flags"])
        for key in ("stable_id", "lesson_name", "lesson_token", "script_name",
                    "displayed_number", "has_objectives", "content_hash"):
            check(f"{ident} lesson.{key}",
                  ar["lesson"][key] == fr["lesson"][key],
                  f"api {ar['lesson'][key]!r} vs fixture {fr['lesson'][key]!r}")

print("\nCoverage")
api = c.get("/api/runs/1/coverage").json()
fixture = strip(fx("coverage"))
for key in ("in_scope", "whole_framework", "buckets", "count_check",
            "umbrella_excluded", "scope_note"):
    check(f"coverage.{key}", api[key] == fixture[key],
          f"api {api[key]!r} vs fixture {fixture[key]!r}")
check("the two percentages differ",
      api["in_scope"]["percent"] != api["whole_framework"]["percent"],
      "scope must visibly change the number")

print("\nThe publish gate")
# One condition now: a person approved the run. The set's boundary state used to
# be a second condition and no longer is - contract/REVIEW-DESIGN.md says why.
# The set below is deliberately one nobody has reviewed, so these checks fail
# if that condition ever creeps back in.
gate_set = next(x for x in c.get("/api/standards-sets").json()["items"]
                if x["id"] == 1)
check("the set under test has boundaries nobody has checked",
      gate_set["boundary_provenance"] != "drafted+reviewed",
      "otherwise this section proves nothing")

check("nothing is public before approval",
      c.get("/public/standards-sets").json()["total"] == 0)
r = c.get("/public/coverage", params={"set_id": 1, "course_id": 1})
check("and public coverage is not served", r.status_code == 404,
      f"got {r.status_code}, expected 404")

r = c.post("/api/runs/1/approve", params={"actor": "test@example.invalid"})
check("a run can be approved though the boundaries were never reviewed",
      r.status_code == 200, f"got {r.status_code}: {r.text[:120]}")
check("approval alone opens the gate",
      c.get("/public/standards-sets").json()["total"] == 1,
      "an approved run is now the whole condition")
r = c.get("/public/coverage", params={"set_id": 1, "course_id": 1})
check("and public coverage is served", r.status_code == 200,
      f"got {r.status_code}: {r.text[:120]}")

print("\nThe identity trio")
r = c.post("/api/standards-sets", json={"filename": "x.pdf", "framework": "DEMO",
                                        "set_type": "standards",
                                        "framework_year": "2026"})
check("a missing standard_set is refused", r.status_code == 422,
      f"got {r.status_code}, expected 422")
check("the refusal names the field",
      any(e.get("loc", [])[-1] == "standard_set" for e in r.json()["detail"]),
      "it must say which of the three is missing")

print("\nReviewer decisions")
r = c.patch("/api/records/5001", json={"review_status": "accepted",
                                       "actor": "test@example.invalid"})
check("a record can be accepted", r.status_code == 200, r.text[:120])
r = c.patch("/api/records/5001", json={"review_status": "rejected",
                                       "actor": "test@example.invalid"})
check("rejecting with no reason is refused", r.status_code == 422,
      f"got {r.status_code}, expected 422")
r = c.patch("/api/records/5005", json={"review_status": "accepted",
                                       "level": "mastered",
                                       "actor": "test@example.invalid"})
check("a choice-level claim cannot be raised", r.status_code == 422,
      f"got {r.status_code}, expected 422")
r = c.patch("/api/records/5007", json={"review_status": "changed",
                                       "level": "introduced",
                                       "actor": "test@example.invalid"})
check("the level can be changed", r.status_code == 200 and
      r.json()["level"] == "introduced", r.text[:120])

print()
print(f"{passes} passed, {len(failures)} failed")
if failures:
    print("\nFailures:")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("The API matches the contract.")
