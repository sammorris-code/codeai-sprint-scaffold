"""Steps 7 to 9 of ingestion: draft the boundaries.

This is the half that needs judgement, so it is the only part that calls a
model. It is kept in one file on purpose: everything else about ingestion is
deterministic, free, and testable without a network.

A boundary says what counts as teaching a standard and what does not. State
frameworks almost never ship one. The quality of an ingestion run is judged on
the quality of these, and a wide boundary produces a silent false positive that
reaches a district, so the instructions below are written to fail narrow.

Nothing here is authoritative. Every boundary it writes is marked `drafted` and
a person checks it once for the set, before any result is published. That gate
is enforced by the service, not by this file.
"""
import os

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5"

# Batched rather than one call per standard. Ten is small enough that each
# statement still gets attention and large enough to keep the run short.
BATCH_SIZE = 10

# Stable, so it caches. Everything that varies goes in the user message, after
# the cache breakpoint.
SYSTEM = """You draft boundary statements for education standards.

A boundary says what counts as teaching a standard, and what does not. It is
used later to decide whether a lesson genuinely addresses the standard, or only
mentions the topic.

Rules, in order of importance:

1. NEVER alter the standard's statement. It is quoted to you word for word and
   must stay that way. You are adding notes about it, not rewriting it.

2. Be conservative. A narrow boundary produces a false negative, which the
   human reviewer catches. A wide boundary produces a false positive, which
   nobody catches and which reaches a school district as a claim we cannot
   defend. Always prefer the recoverable error.

3. The cognitive verb is the spine of the boundary. A standard that says
   "evaluate" must exclude mere exposure. A standard that says "create" must
   require the student to produce something. Read the verb and hold to it.

4. Always write exclusions, even when they feel obvious. Every validated
   false-positive catch has come from an explicit exclusion. Writing none is a
   defect, not a shortcut.

5. When the standard's intent is genuinely unclear, say so inside the boundary
   text. Never guess broad in silence.

6. Keywords are retrieval terms only. They help find candidate lessons. They
   are never sufficient evidence on their own, so do not write them as though
   they were.

7. nearest_csta holds between 0 and 3 CSTA 2026 identifiers that cover similar
   ground. Match on meaning, not on shared vocabulary. An empty list is an
   honest answer and is better than a stretch. This is a drafting aid and an
   audit trail. It is NOT a validated crosswalk and must never be presented as
   one.

When the source supplies its own clarifying text, adapt that text rather than
inventing your own, and it will be recorded as coming from the source."""


class DraftedBoundary(BaseModel):
    identifier: str = Field(description="The standard's identifier, copied exactly.")
    boundary_includes: list[str] = Field(
        min_length=1,
        description="What counts as teaching this. Concrete and observable.")
    boundary_excludes: list[str] = Field(
        min_length=1,
        description="What does not count. The primary defence against a false "
                    "positive. Never leave this empty.")
    keywords: list[str] = Field(
        min_length=1, description="Retrieval terms. Never sufficient evidence.")
    nearest_csta: list[str] = Field(
        default_factory=list, max_length=3,
        description="0 to 3 CSTA 2026 ids covering similar ground. Empty is honest.")
    unclear: str | None = Field(
        default=None,
        description="Set when the standard's intent cannot be read confidently. "
                    "Say what is ambiguous. Do not guess broad in silence.")


class DraftedBatch(BaseModel):
    boundaries: list[DraftedBoundary]


class NoCredentials(RuntimeError):
    """Raised when no API credentials are configured.

    Deliberately not caught and turned into an empty boundary. A fabricated
    boundary is worse than none: it looks like work and it silently widens
    what counts as coverage.
    """


def _client():
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise NoCredentials(
            "Boundary drafting needs an Anthropic API key. Set ANTHROPIC_API_KEY "
            "on the service. Everything else about ingestion runs without one: "
            "the document is already parsed, the statements are extracted word "
            "for word, and the count is reconciled. Only the boundaries are "
            "missing, and they can be drafted later without re-reading the "
            "document.")
    return anthropic.Anthropic()


def _prompt_for(batch):
    lines = []
    for s in batch:
        lines.append(f"Identifier: {s.identifier}")
        lines.append(f"Statement: {s.statement}")
        lines.append(f"Concept: {s.concept}")
        if s.grade_band:
            lines.append(f"Grade band: {s.grade_band}")
        if s.clarification:
            lines.append(f"The source's own clarifying text: {s.clarification}")
        lines.append("")
    return ("Draft a boundary for each of these standards.\n\n" + "\n".join(lines))


def draft_boundaries(standards, progress=None):
    """Draft a boundary for each standard. Returns {identifier: DraftedBoundary}.

    Umbrella headings are skipped. They are rated by rollup from the standards
    beneath them, so a boundary of their own would never be consulted and could
    only mislead.
    """
    client = _client()
    drafting = [s for s in standards if s.hierarchy_role != "umbrella"]
    drafted = {}

    for start in range(0, len(drafting), BATCH_SIZE):
        batch = drafting[start:start + BATCH_SIZE]
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _prompt_for(batch)}],
            output_format=DraftedBatch,
        )
        for b in response.parsed_output.boundaries:
            drafted[b.identifier] = b
        if progress:
            progress(min(start + BATCH_SIZE, len(drafting)), len(drafting),
                     response.usage)

    missing = [s.identifier for s in drafting if s.identifier not in drafted]
    if missing:
        raise RuntimeError(
            f"No boundary came back for {len(missing)} standard(s): "
            f"{', '.join(missing[:5])}. Ingestion stops rather than writing a "
            f"set with silent gaps in it.")
    return drafted


def provenance_for(standard):
    """Where a boundary came from. `source` when the document supplied
    clarifying text we adapted, `drafted` when it did not.

    This is the field the publish gate reads. It is set from the document, not
    from the model's opinion of its own work."""
    return "source" if standard.clarification else "drafted"


# Rough figures for a cost estimate before anybody spends anything. Measure
# exactly with client.messages.count_tokens once credentials exist.
CHARS_PER_TOKEN = 3.7
PRICE_PER_MTOK = {"input": 5.00, "output": 25.00}   # claude-opus-5
OUTPUT_TOKENS_PER_STANDARD = 260


def estimate_cost(standards):
    """An order-of-magnitude estimate, so a spend can be approved before it
    happens. Not a quote."""
    drafting = [s for s in standards if s.hierarchy_role != "umbrella"]
    if not drafting:
        return {"standards": 0, "estimated_usd": 0.0}

    batches = (len(drafting) + BATCH_SIZE - 1) // BATCH_SIZE
    system_tokens = len(SYSTEM) / CHARS_PER_TOKEN
    body_chars = sum(len(s.statement) + len(s.clarification or "") + 80
                     for s in drafting)
    input_tokens = system_tokens * batches + body_chars / CHARS_PER_TOKEN
    output_tokens = OUTPUT_TOKENS_PER_STANDARD * len(drafting)

    usd = (input_tokens / 1e6 * PRICE_PER_MTOK["input"]
           + output_tokens / 1e6 * PRICE_PER_MTOK["output"])
    return {
        "standards": len(drafting),
        "batches": batches,
        "model": MODEL,
        "estimated_input_tokens": round(input_tokens),
        "estimated_output_tokens": round(output_tokens),
        "estimated_usd": round(usd, 2),
        "note": "An estimate from character counts, not a quote. The Batch API "
                "halves it. Measure exactly with count_tokens once a key is set.",
    }
