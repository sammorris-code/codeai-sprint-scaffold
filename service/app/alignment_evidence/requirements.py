"""Versioned requirements grounded in exact state-standard text, not CSTA."""
from .sources import digest


def whole_statements(standards):
    """Safe offline default. Never pretend punctuation can interpret obligations."""
    return [{"standard_id": s["identifier"], "statement": s["statement"],
             "requirements": [{"requirement_id": "R1", "quote": s["statement"]}],
             "interpretation_status": "whole_statement"} for s in standards]


def validate(specs, standards):
    expected = {s["identifier"]: s["statement"] for s in standards}
    if len(specs) != len(expected) or {s["standard_id"] for s in specs} != set(expected):
        raise ValueError("Requirements must include each candidate exactly once.")
    for spec in specs:
        statement = expected[spec["standard_id"]]
        if spec["statement"] != statement:
            raise ValueError("Requirements refer to a different standard statement.")
        reqs = spec["requirements"]
        if not reqs or len({r["requirement_id"] for r in reqs}) != len(reqs):
            raise ValueError("Requirement IDs must be nonempty and unique within a standard.")
        covered = set()
        for req in reqs:
            quote = req["quote"]
            if not req["requirement_id"] or not quote.strip() or quote not in statement:
                raise ValueError("Every requirement must quote the state standard exactly.")
            start = 0
            while (start := statement.find(quote, start)) >= 0:
                covered.update(range(start, start + len(quote)))
                start += 1
        # A decomposition cannot silently discard conditions or parts of a standard.
        if any(c.isalnum() and i not in covered for i, c in enumerate(statement)):
            raise ValueError("Requirement quotes leave part of the statement unrepresented.")
    return digest(specs)


DRAFT_RULES = """Separate each state standard into its independently required
performances. Return exact contiguous quotes whose union covers every word of
the supplied statement, including conditions and scope. Keep compound tasks
together if splitting would destroy their meaning. A single whole-statement
requirement is valid. IDs R1, R2, etc. are local to each standard. Do not add
requirements from CSTA or drafted boundaries. These are proposed interpretations,
not official clarifications. Copy the statement and standard_id exactly."""


def object_schema(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


STRING = {"type": "string"}
DRAFT_SCHEMA = object_schema({"standards": {"type": "array", "items": object_schema({
    "standard_id": STRING, "statement": STRING,
    "requirements": {"type": "array", "items": object_schema({
        "requirement_id": STRING, "quote": STRING})}})}})
