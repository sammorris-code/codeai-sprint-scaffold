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

print("Standards sets")
api = c.get("/api/standards-sets").json()
fixture = strip(fx("standards-sets"))
check("count matches", api["total"] == fixture["total"],
      f"api {api['total']} vs fixture {fixture['total']}")
for a, f in zip(api["items"], fixture["items"]):
    for key in ("framework", "standard_set", "set_type", "framework_year",
                "title", "standard_count", "boundary_provenance", "publishable"):
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
r = c.post("/api/runs/1/approve", params={"actor": "test@example.invalid"})
check("approving an unreviewed set is refused", r.status_code == 409,
      f"got {r.status_code}, expected 409")
check("the refusal names the reason",
      r.json()["detail"]["error"]["code"] == "set_not_reviewed")
r = c.get("/public/coverage", params={"set_id": 1, "course_id": 1})
check("public serves nothing for it", r.status_code == 404,
      f"got {r.status_code}, expected 404")
check("public set list is empty",
      c.get("/public/standards-sets").json()["total"] == 0,
      "no run is approved yet, so nothing may be published")

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
