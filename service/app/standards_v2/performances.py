"""A separate interpretation of required performance, with partial contributions."""
from ..alignment_evidence.requirements import object_schema, STRING, validate as validate_quotes

REQUIREMENT = object_schema({"requirement_id": STRING, "quote": STRING,
    "required_performance": STRING, "action": STRING, "subject": STRING,
    "conditions": STRING, "contributions": {"type": "array", "items": STRING},
    "insufficient_for_full": {"type": "array", "items": STRING},
    "not_evidence": {"type": "array", "items": STRING}})
SCHEMA = object_schema({"standards": {"type": "array", "items": object_schema({
    "standard_id": STRING, "statement": STRING, "integration_required": {"type": "boolean"},
    "integration_reason": STRING, "requirements": {"type": "array", "items": REQUIREMENT}})}})
RULES = """Interpret each supplied state standard's required performance. Keep the
statement verbatim. Quote exact contiguous spans whose union preserves all words.
Describe the action, subject and conditions in the context of the entire statement.
Do not import requirements from CSTA or drafted boundaries. Distinguish useful
contributions (including exposure/prerequisites) from full performance, and
insufficient-for-full from genuinely unrelated evidence. Do not require a written
artifact if a justified discussion satisfies the statement. Examples in the
statement are examples, not an exhaustive required list. Preserve AND/OR meaning.
Set integration_required only when meeting separate components cannot establish
the required relationship (for example, comparing two kinds of security measure).
Name that relationship. Do not atomize a compound action into unrelated fragments.
These interpretations remain proposed, not authoritative source clarifications."""


def validate(specs, standards):
    validate_quotes(specs, standards)
    for spec in specs:
        if not isinstance(spec.get("integration_required"), bool):
            raise ValueError("Required-performance interpretation lacks integration rule")
        if spec["integration_required"] and not spec["integration_reason"].strip():
            raise ValueError("Integration rule needs a reason tied to the standard")
        for requirement in spec["requirements"]:
            for field in ("required_performance", "action", "subject"):
                if not requirement.get(field, "").strip():
                    raise ValueError("Required performance needs action, subject and description")
    return specs
