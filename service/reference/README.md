# CSTA 2026 reference

The anchor. Boundaries for every other framework are drafted against these, and
`nearest_csta` records which ones a drafter looked at.

| File | Holds |
|---|---|
| `csta_foundational_standards.json` | 196 standards, PK-K through 9-12 |
| `csta_specialty_standards.json` | 135 standards, specialty levels S1 and S2 |

Both are labelled *(draft)* by their source. **This repository is public** — if
that is not the right home for them, move the folder somewhere ignored and point
`CSTA_DIR` at it. Nothing else has to change.

## Why this is here at all

Boundary drafting asks the model for `nearest_csta` identifiers. Before this
folder existed it asked without supplying any CSTA standards, so the answer was
either empty or recalled from training — plausible-looking identifiers nobody
could check, sitting in a field whose whole purpose is traceability.

A reference you can point at is the difference between an audit trail and a
guess.

## What gets sent

Only the standards whose grade band overlaps the document being ingested, with
their statements and their own boundary language. For a 9-12 state framework
that is 46 of the 196, about 9.6k tokens, written to the prompt cache once per
run and read cheaply by every batch after the first.

Specialty standards are not sent unless asked for: they describe courses taken
after foundational high school, and a state framework is the wrong thing to
compare them against.
