"""The CSTA 2026 reference — the anchor boundaries are drafted against.

Before this existed, boundary drafting asked the model for `nearest_csta`
identifiers without supplying any CSTA standards. The answer was either empty
or recalled from training: plausible identifiers nobody could verify, sitting in
a field whose only purpose is traceability. This supplies the real thing.

Only the standards whose grade band overlaps the document being ingested are
sent. For a 9-12 state framework that is 46 of the 196, not all of them, which
is both cheaper and better matching - the model is not scanning infant-school
standards looking for an analog to a cybersecurity expectation.
"""
import json
import os
import pathlib
import re

CSTA_DIR = pathlib.Path(os.environ.get(
    "CSTA_DIR", pathlib.Path(__file__).resolve().parents[2] / "reference"))

FOUNDATIONAL = "csta_foundational_standards.json"
SPECIALTY = "csta_specialty_standards.json"

_cache = {}


def _load(filename):
    if filename not in _cache:
        path = CSTA_DIR / filename
        if not path.exists():
            _cache[filename] = []
        else:
            _cache[filename] = json.loads(path.read_text()).get("standards", [])
    return _cache[filename]


def grades_in(band):
    """The set of grade numbers a band label covers.

    Band labels do not agree between frameworks, which is the whole reason this
    exists. CSTA says '9-12'. Oklahoma says '9-10' and '11-12'. Comparing those
    as strings finds nothing, and the reference would silently never be sent.

    PK and K are mapped below zero so they order correctly and never collide
    with a numbered grade.
    """
    if not band:
        return set()
    label = str(band).strip().upper()
    if label in ("PK-K", "PK/K", "PK", "K"):
        return {-1, 0}
    numbers = [int(n) for n in re.findall(r"\d+", label)]
    if not numbers:
        return set()            # S1, S2 and other non-grade levels
    if len(numbers) == 1:
        return {numbers[0]}
    return set(range(min(numbers), max(numbers) + 1))


def reference_for(bands, include_specialty=False):
    """CSTA standards whose grade band overlaps any of `bands`.

    An empty or unreadable set of bands returns everything foundational rather
    than nothing. Sending too much costs a little money; sending nothing
    silently returns the tool to guessing, which is what this fixes.
    """
    wanted = set()
    for b in bands or []:
        wanted |= grades_in(b)

    standards = _load(FOUNDATIONAL)
    if wanted:
        standards = [s for s in standards
                     if grades_in(s.get("grade_band")) & wanted] or standards
    if include_specialty:
        standards = standards + _load(SPECIALTY)
    return standards


def as_prompt(standards):
    """The reference as the model sees it.

    Carries each standard's own boundary language, because a close analog is
    meant to be adapted rather than described. That is the whole value of
    having an anchor that ships boundaries when state frameworks do not.
    """
    if not standards:
        return None
    lines = [
        "CSTA 2026 reference. Use these when looking for a nearest analog, and "
        "adapt their boundary language to the state statement's scope when one "
        "is close. Only these identifiers exist; never write one that is not "
        "listed here.",
        "",
    ]
    for s in standards:
        lines.append(f"{s['id']} [{s.get('concept') or s.get('specialty_area', '')}"
                     f"{' / ' + s['subconcept'] if s.get('subconcept') else ''}]")
        lines.append(f"  {s['statement']}")
        if s.get("boundary_includes"):
            lines.append(f"  Counts: {s['boundary_includes']}")
        if s.get("boundary_excludes"):
            lines.append(f"  Does not count: {s['boundary_excludes']}")
        lines.append("")
    return "\n".join(lines)


def valid_ids(standards):
    """For checking what came back. An identifier the model invented is worse
    than an empty list, so the caller drops anything not in here."""
    return {s["id"] for s in standards}
