"""Step 1 to 6 of ingestion: read the document and report what is in it.

This half is deterministic. It parses, extracts statements word for word,
works out the identifier scheme, and reconciles the count. It makes no
judgements, so it needs no model and costs nothing to run.

It deliberately stops before drafting boundaries. That is the half that needs
judgement, and it lives in boundaries.py.

Two rules from the briefing are enforced here rather than trusted:

  - Statements are copied word for word. Any paraphrase is a defect, so this
    code never rewrites one; it only strips surrounding whitespace.
  - The count is reconciled. A silent extraction gap poisons everything
    downstream, so a mismatch is reported and the caller must stop.
"""
import csv
import io
import re
from dataclasses import dataclass, field, asdict

# Column names seen in the wild, lowest-effort first. A source that uses none
# of these is reported rather than guessed at.
COLUMN_ALIASES = {
    "identifier": ["code", "identifier", "id", "standard id", "standard code",
                   "number", "reference"],
    "statement": ["standard", "statement", "description", "text",
                  "standard statement", "expectation"],
    "concept": ["strand", "concept", "domain", "category", "area", "cluster"],
    "subconcept": ["subconcept", "sub-strand", "substrand", "topic"],
    "grade_band": ["grade band", "grade", "grades", "level", "band"],
    "clarification": ["clarification", "clarifying statement", "note", "notes",
                      "guidance", "boundary"],
}


@dataclass
class ExtractedStandard:
    identifier: str
    statement: str
    concept: str
    subconcept: str | None = None
    grade_band: str | None = None
    clarification: str | None = None
    hierarchy_role: str = "standard"
    rating_rule: str = "direct"
    parent_identifier: str | None = None


@dataclass
class Characterization:
    """What the document turned out to contain. Reported before anything is
    written, so a person can confirm the scope."""
    identifier_scheme: str
    concepts: list[str]
    grade_bands: list[str]
    extracted_count: int
    document_claims_count: int | None
    count_reconciled: bool
    has_umbrella_rows: bool
    umbrella_count: int
    clarification_count: int
    boundary_source: dict
    warnings: list[str] = field(default_factory=list)
    standards: list[ExtractedStandard] = field(default_factory=list)

    def as_report(self):
        """The payload the interface shows. Leaves the standards out; they are
        long and the reviewer confirms scope, not content, at this point."""
        d = asdict(self)
        d.pop("standards")
        d["awaiting"] = "scope_confirmation"
        return d


def _map_columns(header):
    """Work out which column is which. Returns (mapping, unmatched headers)."""
    lowered = {h.strip().lower(): h for h in header if h}
    mapping = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field_name] = lowered[alias]
                break
    used = set(mapping.values())
    return mapping, [h for h in header if h and h not in used]


def _describe_scheme(identifiers):
    """Describe the identifier pattern in the document's own terms.

    Never invents a scheme. The useful signal is not "how many shapes are
    there" but "which identifiers differ from the rest", because a stray one is
    almost always a typo in the source - and a typo in an identifier silently
    breaks every join made against it later.

    So: normalise runs of letters to A and runs of digits to N, find the
    dominant shape, and name the outliers.

    An earlier version normalised only single letters, which reported a clean
    55-row state framework as "14 identifier shapes present". That is a false
    alarm, and a reviewer who learns to wave this line through will wave
    through the real one.
    """
    if not identifiers:
        return "No identifiers found in the source."

    def shape(i):
        i = re.sub(r"[A-Za-z]+", "A", i)
        return re.sub(r"\d+", "N", i)

    shapes = {}
    for i in identifiers:
        shapes.setdefault(shape(i), []).append(i)

    if len(shapes) == 1:
        only = next(iter(shapes))
        return (f"All {len(identifiers)} identifiers follow the pattern {only} "
                f"(A is letters, N is digits).")

    ranked = sorted(shapes.items(), key=lambda kv: -len(kv[1]))
    main_shape, main_ids = ranked[0]
    outliers = [i for _, ids in ranked[1:] for i in ids]

    # A handful of strays against a clear majority: name them. This is the
    # case that catches an OCR artefact or a mistyped identifier.
    if len(outliers) <= max(5, len(identifiers) // 10):
        listed = ", ".join(outliers[:5])
        more = f" and {len(outliers) - 5} more" if len(outliers) > 5 else ""
        return (f"{len(main_ids)} of {len(identifiers)} identifiers follow the "
                f"pattern {main_shape} (A is letters, N is digits). "
                f"{len(outliers)} differ: {listed}{more}. Check these against "
                f"the source - a stray identifier is usually a typo there, and "
                f"it is copied verbatim rather than corrected.")

    return (f"{len(shapes)} identifier shapes present, the commonest being "
            f"{main_shape} ({len(main_ids)} of {len(identifiers)}). Confirm "
            f"this is intended before continuing.")


def characterize_csv(raw: bytes, claimed_count: int | None = None) -> Characterization:
    """Read a CSV of standards and report what is in it.

    utf-8-sig, not utf-8. A byte-order mark on the first header turns 'Code'
    into '\\ufeffCode', the column match then fails, and every identifier comes
    back empty. This has cost a whole run before.
    """
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    mapping, unmatched = _map_columns(header)

    warnings = []
    for required in ("identifier", "statement"):
        if required not in mapping:
            raise ValueError(
                f"No column in this document looks like the {required}. "
                f"Columns found: {', '.join(header) or '(none)'}. "
                f"Rename a column to one of: {', '.join(COLUMN_ALIASES[required])}."
            )
    if "concept" not in mapping:
        warnings.append(
            "No concept or strand column found. Every standard is filed under "
            "'Uncategorised', which makes scope filtering useless. Add one "
            "before running an alignment.")
    if unmatched:
        warnings.append(
            f"These columns were not used: {', '.join(unmatched)}. "
            f"Check nothing important was dropped.")

    standards, blank_rows = [], 0
    for row in reader:
        identifier = (row.get(mapping["identifier"]) or "").strip()
        statement = (row.get(mapping["statement"]) or "").strip()
        if not identifier and not statement:
            blank_rows += 1
            continue
        if not identifier:
            warnings.append(f"A row has a statement but no identifier: "
                            f"{statement[:60]!r}. It was skipped.")
            continue
        if not statement:
            warnings.append(f"{identifier} has no statement text. It was skipped.")
            continue

        def col(name):
            key = mapping.get(name)
            value = (row.get(key) or "").strip() if key else ""
            return value or None

        standards.append(ExtractedStandard(
            identifier=identifier,
            statement=statement,          # word for word. Never rewritten.
            concept=col("concept") or "Uncategorised",
            subconcept=col("subconcept"),
            grade_band=col("grade_band"),
            clarification=col("clarification"),
        ))

    _mark_hierarchy(standards)

    identifiers = [s.identifier for s in standards]
    duplicates = {i for i in identifiers if identifiers.count(i) > 1}
    if duplicates:
        warnings.append(
            f"Duplicate identifiers: {', '.join(sorted(duplicates))}. "
            f"Identifiers must be unique inside one set.")

    umbrellas = [s for s in standards if s.hierarchy_role == "umbrella"]
    if umbrellas:
        warnings.append(
            f"{len(umbrellas)} row(s) look like headings rather than standards "
            f"({', '.join(s.identifier for s in umbrellas)}). They are marked to "
            f"be rated by rollup and excluded from coverage totals. Counting "
            f"them as well double-counts.")

    with_clarification = sum(1 for s in standards if s.clarification)
    if with_clarification == 0:
        warnings.append(
            "The source carries no clarifying text, so every boundary must be "
            "drafted from the statement alone. Drafted boundaries are "
            "conservative by design, and a person must check them before any "
            "result reaches a district.")

    # None, not True, when there is nothing to check against. A green light
    # for a check that never ran is worse than no light at all.
    reconciled = None if claimed_count is None else claimed_count == len(standards)
    if reconciled is None:
        warnings.append(
            "No claimed count was given, so the extraction was not reconciled "
            "against anything. Find the total the document states and pass it "
            "as claimed_count: a silent extraction gap is the failure that "
            "poisons everything downstream, and this is the only check for it.")
    elif not reconciled:
        warnings.append(
            f"The document claims {claimed_count} standards. {len(standards)} "
            f"were extracted. Stop and find the difference before continuing: "
            f"a silent extraction gap poisons everything downstream.")
    if blank_rows:
        warnings.append(f"{blank_rows} blank row(s) were skipped.")

    return Characterization(
        identifier_scheme=_describe_scheme(identifiers),
        concepts=sorted({s.concept for s in standards}),
        grade_bands=sorted({s.grade_band for s in standards if s.grade_band}),
        extracted_count=len(standards),
        document_claims_count=claimed_count,
        count_reconciled=reconciled,
        has_umbrella_rows=bool(umbrellas),
        umbrella_count=len(umbrellas),
        clarification_count=with_clarification,
        boundary_source={"source": with_clarification,
                         "drafted": len(standards) - with_clarification},
        warnings=warnings,
        standards=standards,
    )


def _mark_hierarchy(standards):
    """Find heading rows and the standards beneath them.

    A heading is a row whose identifier ends in .0 — the convention in every
    hierarchical framework seen so far. A heading is rated by rollup from its
    children and never on its own, because rating it as well double-counts.
    """
    by_prefix = {}
    for s in standards:
        if s.identifier.endswith(".0"):
            s.hierarchy_role = "umbrella"
            s.rating_rule = "rollup"
            by_prefix[s.identifier[:-2]] = s.identifier

    for s in standards:
        if s.hierarchy_role == "umbrella":
            continue
        prefix = s.identifier.rsplit(".", 1)[0]
        if prefix in by_prefix:
            s.parent_identifier = by_prefix[prefix]
