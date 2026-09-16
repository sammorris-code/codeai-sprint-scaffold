#!/usr/bin/env python3
"""Check every fixture against its schema, and check the rules between fixtures.

No install. Standard library only. Run it before you commit a change here:

    python3 contract/validate.py

It does three passes:
  1. Shape    - each fixture matches its JSON Schema.
  2. Rules    - the invariants that no single schema can express.
  3. Hygiene  - nothing here names a real place or a real number.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_DIR = HERE / "schema"
FIXTURE_DIR = HERE / "fixtures"

errors = []
checks = 0


def fail(where, message):
    errors.append(f"{where}: {message}")


# --------------------------------------------------------------------------
# Pass 1. A small JSON Schema checker, covering the subset these schemas use.
# --------------------------------------------------------------------------

_schema_cache = {}

TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
         "object": dict, "array": list, "null": type(None)}


def load_schema(name):
    if name not in _schema_cache:
        _schema_cache[name] = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    return _schema_cache[name]


def check_type(value, expected):
    names = expected if isinstance(expected, list) else [expected]
    for n in names:
        py = TYPES.get(n)
        if py is None:
            return True
        # bool is a subclass of int in Python; do not let True pass as integer
        if n in ("integer", "number") and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def validate(value, schema, path, where):
    global checks
    checks += 1

    if "$ref" in schema:
        validate(value, load_schema(schema["$ref"]), path, where)
        return

    if "const" in schema and value != schema["const"]:
        fail(where, f"{path}: expected {schema['const']!r}, found {value!r}")

    if "type" in schema and not check_type(value, schema["type"]):
        fail(where, f"{path}: expected type {schema['type']}, found {type(value).__name__}")
        return

    if "enum" in schema and value not in schema["enum"]:
        fail(where, f"{path}: {value!r} is not one of {schema['enum']}")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            fail(where, f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            fail(where, f"{path}: {value!r} does not match {schema['pattern']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            fail(where, f"{path}: needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            fail(where, f"{path}: allows at most {schema['maxItems']} items")
        if "items" in schema:
            for i, entry in enumerate(value):
                validate(entry, schema["items"], f"{path}[{i}]", where)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            fail(where, f"{path}: below minimum {schema['minimum']}")

    if isinstance(value, dict):
        for field in schema.get("required", []):
            if field not in value:
                fail(where, f"{path}: required field {field!r} is missing")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props and not key.startswith("_"):
                    fail(where, f"{path}: unexpected field {key!r}")
        for key, sub in props.items():
            if key in value:
                target = sub
                if "$defs" in schema and "$ref" in sub and sub["$ref"].startswith("#/$defs/"):
                    target = schema["$defs"][sub["$ref"].split("/")[-1]]
                elif "items" in sub and isinstance(sub["items"], dict) \
                        and sub["items"].get("$ref", "").startswith("#/$defs/"):
                    target = dict(sub)
                    target["items"] = schema["$defs"][sub["items"]["$ref"].split("/")[-1]]
                validate(value[key], target, f"{path}.{key}", where)

    for sub in schema.get("allOf", []):
        if "if" in sub:
            probe = []
            saved, errors[:] = errors[:], []
            validate(value, sub["if"], path, where)
            matched = not errors
            errors[:] = saved
            if matched and "then" in sub:
                validate(value, sub["then"], path, where)
        else:
            validate(value, sub, path, where)

    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            saved, errors[:] = errors[:], []
            validate(value, sub, path, where)
            ok = not errors
            errors[:] = saved
            if ok:
                break
        else:
            fail(where, f"{path}: matches none of the allowed shapes")


def fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


print("Pass 1  shape")

for i, s in enumerate(fixture("standards-sets.json")["items"]):
    validate(s, load_schema("standards-set.schema.json"), f"items[{i}]", "standards-sets.json")

for i, s in enumerate(fixture("standards.json")["items"]):
    validate(s, load_schema("standard.schema.json"), f"items[{i}]", "standards.json")

for i, l in enumerate(fixture("lessons.json")["items"]):
    validate(l, load_schema("lesson.schema.json"), f"items[{i}]", "lessons.json")

validate(fixture("run.json"), load_schema("run.schema.json"), "run", "run.json")

queue = fixture("review-queue.json")
for i, item in enumerate(queue["items"]):
    validate(item["outcome"], load_schema("standard-outcome.schema.json"),
             f"items[{i}].outcome", "review-queue.json")
    for j, r in enumerate(item["records"]):
        validate(r, load_schema("alignment-record.schema.json"),
                 f"items[{i}].records[{j}]", "review-queue.json")

print(f"        {checks} nodes checked")


# --------------------------------------------------------------------------
# Pass 2. The rules no single schema can express.
# --------------------------------------------------------------------------

print("Pass 2  rules")

sets = fixture("standards-sets.json")["items"]
lessons = {l["stable_id"]: l for l in fixture("lessons.json")["items"]}
coverage = fixture("coverage.json")
public = fixture("public-coverage.json")
diff = fixture("run-diff.json")

# all_boundaries_checked is computed from boundary_provenance, never asserted.
# It reports whether a person has checked every boundary in the set. It does
# NOT gate publishing - see REVIEW-DESIGN.md.
for s in sets:
    want = s["boundary_provenance"] == "drafted+reviewed"
    if s["all_boundaries_checked"] != want:
        fail("standards-sets.json",
             f"{s['framework']}/{s['standard_set']}: all_boundaries_checked is {s['all_boundaries_checked']} "
             f"but provenance is {s['boundary_provenance']!r}")

# At least one set must have unchecked boundaries, or the screen that shows
# that state has nothing to show.
if not any(not s["all_boundaries_checked"] for s in sets):
    fail("standards-sets.json", "every set has all its boundaries checked; the "
         "unchecked state cannot be built against")

# Umbrella rows carry no records of their own.
for item in queue["items"]:
    ident = item["standard"]["identifier"]
    if item["standard"]["hierarchy_role"] == "umbrella":
        if item["records"]:
            fail("review-queue.json", f"{ident}: an umbrella row must hold no records")
        if item["standard"]["rating_rule"] != "rollup":
            fail("review-queue.json", f"{ident}: an umbrella row must be rated by rollup")
    # A choice-level claim is capped and names its branch.
    for r in item["records"]:
        if r["is_choice_level"]:
            if r["level"] != "introduced":
                fail("review-queue.json", f"{ident}: a choice-level claim must cap at introduced")
            if not r["choice_option"]:
                fail("review-queue.json", f"{ident}: a choice-level claim must name its option")
        # Every record points at a lesson that exists in the snapshot.
        if r["lesson"]["stable_id"] not in lessons:
            fail("review-queue.json", f"{ident}: unknown lesson {r['lesson']['stable_id']}")
        # A record whose stored hash differs from the lesson's current hash is stale.
        current = lessons.get(r["lesson"]["stable_id"], {}).get("content_hash")
        drifted = current is not None and r["lesson_content_hash"] != current
        if drifted and r["review_status"] != "stale":
            fail("review-queue.json",
                 f"{ident}: hash differs from the snapshot but review_status is "
                 f"{r['review_status']!r}, not 'stale'")
        if r["review_status"] == "stale" and not drifted:
            fail("review-queue.json", f"{ident}: marked stale but the hash matches")

# The count check, recomputed rather than trusted.
countable = [i for i in queue["items"] if i["standard"]["hierarchy_role"] != "umbrella"]
in_scope = [i for i in countable if i["outcome"]["in_scope"]]
tally = {}
for i in in_scope:
    tally[i["outcome"]["outcome"]] = tally.get(i["outcome"]["outcome"], 0) + 1
if tally != {k: v for k, v in coverage["buckets"].items() if v}:
    fail("coverage.json", f"buckets {coverage['buckets']} do not match the queue {tally}")
if sum(coverage["buckets"].values()) != len(in_scope):
    fail("coverage.json", "the six buckets do not sum to the candidate set")
if not coverage["count_check"]["ok"]:
    fail("coverage.json", "count_check.ok is false")
if coverage["in_scope"]["total"] != len(in_scope):
    fail("coverage.json", "in_scope total disagrees with the queue")
if coverage["whole_framework"]["total"] != len(countable):
    fail("coverage.json", "whole_framework total disagrees with the queue")
if coverage["in_scope"]["percent"] == coverage["whole_framework"]["percent"]:
    fail("coverage.json",
         "both percentages are equal; the fixture must show that scope changes the number")
if not coverage.get("scope_note"):
    fail("coverage.json", "scope_note is missing; a percentage without scope is a wrong number")

# The public payload leaks nothing.
LEAKS = ("rationale", "flags", "reviewed_by", "reviewed_on", "evidence")
for row in public["rows"]:
    for key in LEAKS:
        if key in row:
            fail("public-coverage.json", f"row leaks {key!r}")
if not public.get("scope_note"):
    fail("public-coverage.json", "scope_note is missing")
if not any(r["outcome"] == "not_addressed" for r in public["rows"]):
    fail("public-coverage.json", "no not_addressed row; the gap decision must be visible in one place")

# The diff reports a real drift.
for s in diff["stale"]:
    cur = lessons.get(s["lesson_stable_id"], {}).get("content_hash")
    if s["now_hash"] != cur:
        fail("run-diff.json", f"{s['lesson_stable_id']}: now_hash is not the snapshot's hash")
    if s["was_hash"] == s["now_hash"]:
        fail("run-diff.json", f"{s['lesson_stable_id']}: was_hash equals now_hash")

# The trap cases must survive an edit to the fixtures.
required_cases = {
    "a unit with a blank displayed_number":
        any(l.get("displayed_number") == "" for l in lessons.values()),
    "a non-numeric lesson token":
        any(not l["lesson_token"].isdigit() for l in lessons.values()),
    "a lesson with no authored objective":
        any(not l["has_objectives"] for l in lessons.values()),
    "a lesson_key that is a former title":
        any(l["lesson_key"] not in l["lesson_name"].lower().replace(" ", "-")
            for l in lessons.values()),
    "a standard with no evidence":
        any(not i["records"] for i in queue["items"]),
    "a boundary_issue outcome":
        any(i["outcome"]["outcome"] == "boundary_issue" for i in queue["items"]),
    "a program requirement":
        any(i["outcome"]["outcome"] == "not_curriculum_addressable" for i in queue["items"]),
    "an out-of-scope standard":
        any(not i["outcome"]["in_scope"] for i in queue["items"]),
    "a stale record":
        any(r["review_status"] == "stale" for i in queue["items"] for r in i["records"]),
    "both flag kinds":
        {f["kind"] for i in queue["items"] for r in i["records"] for f in r["flags"]}
        >= {"depth_doubt", "weak_match"},
    "an empty set list":
        (FIXTURE_DIR / "standards-sets-empty.json").exists(),
}
for case, present in required_cases.items():
    if not present:
        fail("fixtures", f"lost a trap case: {case}")

print(f"        {len(required_cases)} trap cases present")


# --------------------------------------------------------------------------
# Pass 3. Hygiene. This repository is public.
# --------------------------------------------------------------------------

print("Pass 3  hygiene")

# A real place or a real course must never appear in invented data. A screenshot
# of a demo must not read as a claim.
#
# CSTA is not on this list, on purpose. It is the anchor: the reference the
# boundaries are drafted against, and the name of a real contract field
# (nearest_csta). Naming the anchor is correct. Naming a state is not.
BANNED = ["arizona", "texas", "california", "oklahoma", "indiana",
          "north carolina", "teks", "kpas",
          "ai foundations", "ai discoveries", "code.org", "codeai"]
ALLOWED_FILES = {"snapshots.json"}  # names the upstream repository, which is correct


def walk_values(node):
    """Yield every string VALUE. Field names are part of the contract, not data."""
    if isinstance(node, dict):
        for v in node.values():
            yield from walk_values(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_values(v)
    elif isinstance(node, str):
        yield node


for path in sorted(FIXTURE_DIR.glob("*.json")):
    if path.name in ALLOWED_FILES:
        continue
    for value in walk_values(json.loads(path.read_text(encoding="utf-8"))):
        low = value.lower()
        for word in BANNED:
            if word in low:
                fail(path.name, f"names a real place or course: {word!r}. Use DEMO.")

print(f"        {len(BANNED)} banned terms checked in values")


# --------------------------------------------------------------------------

print()
if errors:
    print(f"FAILED  {len(errors)} problem(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("OK      every fixture matches its schema and its rules")
