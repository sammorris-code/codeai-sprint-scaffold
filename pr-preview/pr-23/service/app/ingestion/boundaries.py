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
import pydantic
from pydantic import BaseModel, Field

from . import csta

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

7. nearest_csta holds between 0 and 3 identifiers, taken ONLY from the CSTA
   reference given to you below. Never write an identifier that is not in that
   list.

   The purpose of a nearest analog is to give you boundary language worth
   adapting. So the test is simply: WOULD YOU ACTUALLY ADAPT THIS STANDARD'S
   BOUNDARY WORDING for the statement in front of you? If you would not, it is
   not a nearest analog, and the answer is an empty list.

   Most state standards have no close CSTA analog. An empty list is the common
   and expected answer, not a failure to find something. Returning a loose
   match on every standard turns this field into a crosswalk, which is exactly
   what it must never be: it is a drafting aid and an audit trail.

   Two traps. Sharing a word is not being near - a standard about procedural
   abstraction in algorithms is not an analog for one about abstraction hiding
   implementation detail in an embedded device. And sitting in a related area
   is not being near either - a standard about evaluating a design against its
   specification is not an analog for one about troubleshooting faults, even
   though both concern testing.

8. No line may repeat another. Every inclusion and every exclusion must be able
   to change a decision on its own: if a reviewer deleted it, some lesson would
   be judged differently. Two lines saying the same thing in different words is
   one line and some noise.

   This is NOT an instruction to be brief. A short vague boundary is the worst
   possible outcome - it is the thing that lets a topic match count as
   coverage. Be as specific as the standard demands, then stop repeating
   yourself. Typically two or three inclusions (the action, the scope, the
   evidence) and three to six exclusions, each naming a different way a lesson
   could look like a match without being one.

When the source supplies its own clarifying text, adapt that text rather than
inventing your own, and it will be recorded as coming from the source.

When a CSTA standard below is a close analog, adapt its boundary language to
the scope of the statement in front of you rather than writing from scratch.
That is what the reference is for."""


class DraftedBoundary(BaseModel):
    identifier: str = Field(description="The standard's identifier, copied exactly.")
    # The bounds here are a sanity check for runaway output, NOT the style
    # rule. The style rule - no line repeating another, usually two or three
    # inclusions - lives in the prompt, where it belongs.
    #
    # An earlier version capped inclusions at three and a standard came back
    # with four. Four is not wrong: some statements genuinely have four facets.
    # But the cap was hard, so Pydantic rejected the batch, the batch took nine
    # other standards down with it, and the whole run failed after several
    # batches had already been paid for. A schema cannot judge redundancy, so
    # counting was a proxy for a thing it does not measure.
    boundary_includes: list[str] = Field(
        min_length=1, max_length=6,
        description="What counts as teaching this. Concrete and observable. "
                    "Usually two or three: the action, the scope, the "
                    "evidence. No line repeating another.")
    boundary_excludes: list[str] = Field(
        min_length=2, max_length=8,
        description="What does not count. The primary defence against a false "
                    "positive. Each must name a DIFFERENT way a lesson could "
                    "look like a match without being one. Never empty.")
    keywords: list[str] = Field(
        min_length=1, description="Retrieval terms. Never sufficient evidence.")
    nearest_csta: list[str] = Field(
        default_factory=list, max_length=3,
        description="0 to 3 ids taken only from the CSTA reference supplied. "
                    "Never invent one. Empty is honest.")
    unclear: str | None = Field(
        default=None,
        description="Set when the standard's intent cannot be read confidently. "
                    "Say what is ambiguous. Do not guess broad in silence.")


class DraftedBatch(BaseModel):
    boundaries: list[DraftedBoundary]


class BoundaryRefused(RuntimeError):
    """One standard's boundary would not fit the schema, even on its own.

    The batch is split down to single standards before this is raised, so the
    identifier here is the actual culprit rather than "one of these ten".
    """

    def __init__(self, identifier, statement, cause):
        self.identifier = identifier
        super().__init__(
            f"The boundary drafted for {identifier} does not fit the schema, "
            f"and it still did not when drafted on its own. Nothing was "
            f"written.\n\n"
            f"  {identifier}: {statement[:150]}\n\n"
            f"Every other standard drafted fine. If this statement is unusual "
            f"- very long, several requirements in one sentence, or malformed "
            f"in the source - that is the place to look.\n\n{cause}")


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


def _system_blocks(reference_text):
    """Rules first, then the CSTA reference, with the cache breakpoint last.

    Both are identical across every batch in a run, so the whole prefix is
    written to the cache once and read cheaply by the batches after the first.
    Everything that varies - the standards themselves - goes in the user
    message, after the breakpoint.
    """
    blocks = [{"type": "text", "text": SYSTEM}]
    if reference_text:
        blocks.append({"type": "text", "text": reference_text})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def draft_boundaries(standards, progress=None, include_specialty=False):
    """Draft a boundary for each standard. Returns {identifier: DraftedBoundary}.

    Umbrella headings are skipped. They are rated by rollup from the standards
    beneath them, so a boundary of their own would never be consulted and could
    only mislead.
    """
    client = _client()
    drafting = [s for s in standards if s.hierarchy_role != "umbrella"]
    drafted = {}

    # Only the CSTA standards whose grade band overlaps this document. For a
    # 9-12 state framework that is 46 of the 196.
    bands = {s.grade_band for s in drafting if s.grade_band}
    reference = csta.reference_for(bands, include_specialty)
    reference_text = csta.as_prompt(reference)
    known_ids = csta.valid_ids(reference)
    system = _system_blocks(reference_text)
    invented = set()

    def ask(batch):
        """One call. On a validation error the batch is split and re-asked,
        halving down to single standards.

        Output that does not fit the schema is usually one standard's doing.
        Losing ten of them - and every batch already paid for - because of one
        is not a trade worth making. Splitting isolates the culprit and the
        rest still get drafted.
        """
        try:
            return client.messages.parse(
                model=MODEL, max_tokens=16000, system=system,
                messages=[{"role": "user", "content": _prompt_for(batch)}],
                output_format=DraftedBatch,
            )
        except pydantic.ValidationError as e:
            if len(batch) == 1:
                # Down to one standard and still failing, so we know exactly
                # which. Say so: "one of these ten" sends somebody hunting.
                raise BoundaryRefused(batch[0].identifier, batch[0].statement, e)
            return None      # tell the caller to split

    def collect(batch, into):
        response = ask(batch)
        if response is None:
            half = max(len(batch) // 2, 1)
            collect(batch[:half], into)
            collect(batch[half:], into)
            return
        into.append(response)

    for start in range(0, len(drafting), BATCH_SIZE):
        batch = drafting[start:start + BATCH_SIZE]
        responses = []
        collect(batch, responses)
        response = responses[-1]
        for b in [x for r in responses for x in r.parsed_output.boundaries]:
            # An identifier the model invented is worse than an empty list: it
            # looks like an audit trail and is not one. Drop it and say so.
            if known_ids:
                bad = [i for i in b.nearest_csta if i not in known_ids]
                if bad:
                    invented.update(bad)
                    b.nearest_csta = [i for i in b.nearest_csta if i in known_ids]
            drafted[b.identifier] = b
        if progress:
            progress(min(start + BATCH_SIZE, len(drafting)), len(drafting),
                     response.usage)

    if invented:
        print(f"Dropped {len(invented)} CSTA identifier(s) that are not in the "
              f"reference: {', '.join(sorted(invented)[:8])}")

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
# claude-opus-5. Cache write is 1.25x input and cache read 0.1x, the standard
# multipliers; confirm against current pricing before quoting these to anybody.
PRICE_PER_MTOK = {"input": 5.00, "output": 25.00,
                  "cache_write": 6.25, "cache_read": 0.50}
OUTPUT_TOKENS_PER_STANDARD = 260


def estimate_cost(standards):
    """An order-of-magnitude estimate, so a spend can be approved before it
    happens. Not a quote."""
    drafting = [s for s in standards if s.hierarchy_role != "umbrella"]
    if not drafting:
        return {"standards": 0, "estimated_usd": 0.0}

    batches = (len(drafting) + BATCH_SIZE - 1) // BATCH_SIZE

    bands = {s.grade_band for s in drafting if s.grade_band}
    reference = csta.reference_for(bands)
    reference_tokens = len(csta.as_prompt(reference) or "") / CHARS_PER_TOKEN

    system_tokens = len(SYSTEM) / CHARS_PER_TOKEN
    body_chars = sum(len(s.statement) + len(s.clarification or "") + 80
                     for s in drafting)

    # The rules and the reference are identical every batch, so they are
    # written to the cache once and read by the rest. Without caching the
    # reference would be re-sent six times over and dominate the bill.
    cached = system_tokens + reference_tokens
    fresh = body_chars / CHARS_PER_TOKEN
    output_tokens = OUTPUT_TOKENS_PER_STANDARD * len(drafting)

    usd = (cached / 1e6 * PRICE_PER_MTOK["cache_write"]
           + cached * max(batches - 1, 0) / 1e6 * PRICE_PER_MTOK["cache_read"]
           + fresh / 1e6 * PRICE_PER_MTOK["input"]
           + output_tokens / 1e6 * PRICE_PER_MTOK["output"])
    return {
        "standards": len(drafting),
        "batches": batches,
        "model": MODEL,
        "csta_reference_standards": len(reference),
        "estimated_input_tokens": round(cached + fresh),
        "estimated_output_tokens": round(output_tokens),
        "estimated_usd": round(usd, 2),
        "note": "An estimate from character counts, not a quote. The Batch API "
                "halves it. Measure exactly with count_tokens once a key is set.",
    }
