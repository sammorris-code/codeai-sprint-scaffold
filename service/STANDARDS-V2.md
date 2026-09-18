# Lesson, unit and course alignment

The v2 workflow adds a synthesized evidence layer alongside the immutable raw
curriculum. Lessons contribute, units connect and demonstrate, and course
coverage is computed over actual student pathways. The original alignment and
comparison commands remain available. Nothing is automatically published.

## Architecture

1. **Raw corpus:** extraction retains plans and student screens and also writes
   `evidence/<unit>/<lesson>.sources.json` with complete source passages and
   locations. No paid calls occur during extraction.
2. **Instructional inventory:** a model synthesizes framework-independent
   instructional items (exposure, practice, artifacts, assessments). Each carries
   an action, subject, expected artifact, independence, exact source quotations,
   lesson identity, and pathway conditions. Every raw source must be accounted
   for as captured, background, or unclear. Source quotations and conditions are
   checked in code. Objectives alone cannot substantiate instruction.
3. **Unit synthesis:** a separately cached, framework-independent description
   links items into an instructional sequence and identifies visible culminating
   work. It never invents what a project assesses. Its item references are checked.
4. **Required performances:** the state statement is preserved; each proposed
   interpretation distinguishes required action, subject and conditions, useful
   contributions, insufficient-for-full evidence, and unrelated evidence. Exact
   requirement quotes must collectively represent the entire original statement.
   CSTA and drafted exclusions do not add obligations. Where separate components
   cannot establish a required relationship, an explicit integration witness is
   required. This stage is a new interpretation layer; legacy boundaries survive.
5. **Broad discovery and qualification:** every lesson inventory is considered
   against the full candidate set. No keyword filter or fixed claim-count cap is
   used. Candidate pairs receive requirement-level findings. Exposure and
   prerequisites are retained separately from performance coverage.
6. **Standard-first unit review:** every candidate standard is reviewed across
   each unit's available inventory, including standards missed by discovery.
   This is the recall safeguard. It can recover contributions across lessons,
   but its evidence must point to actual instructional items.
7. **Unit and course aggregation:** code combines complementary full requirements,
   retaining the chain from course to unit to lesson to source. Repeated partial
   work is never promoted to full. Course aggregation uses the original conditions,
   not a lossy maximum of unit ratings.

All semantic interpretations remain proposed. Code proves quotation presence,
identity consistency and pathway compatibility, not educational validity.

## Pathway semantics

An evidence set is a conjunction: the student must receive all its items. Multiple
sets are alternative ways to evidence the same performance. Authored choice
metadata supplies route variables, including nested choices and bonus work.

If both small-grid and large-grid options require a performance, one evidence set
per option can establish that it is shared. If one option teaches design and
another teaches testing, their union cannot establish that any student did both.

Optional work includes a skip route. An unresolved alternate lesson is treated
conservatively as optional and flagged. The system does not infer which regular
lesson it replaces. For actual whole-lesson or unit alternatives, provide explicit
route conditions (apply the same condition to each lesson in an optional unit):

```json
{
  "domains": {"implementation_track": ["python", "web"]},
  "lessons": {
    "example-unit::Python project": {"implementation_track": "python"},
    "example-unit::Web project": {"implementation_track": "web"}
  }
}
```

Pass this file with `--pathways`. Unlisted regular lessons remain shared. Do not
omit a lesson that is replaced on one route. Formula search is bounded; exhaustion
returns unknown, never guaranteed coverage.

For standards requiring integration, v2 accepts an explicit same-lesson task
witness; related activities in other lessons cannot manufacture that witness.
A genuinely integrated project spanning separately recorded lessons needs review
and a future explicit shared-artifact relation. Component coverage remains visible.

## Prepare and inspect: no model key or paid calls

From the repository root, with dependencies from `service/requirements.txt`:

```bash
python service/standards_pipeline.py --baseline-run 3 --human-run 8 \
  --out runs/v2-prepared
```

Set `DATABASE_URL` to an isolated database restored from the dump. Alternatively,
pass `--dataset runs/local-dataset.json`, exported with the older comparison
command. The baseline run pins the course, snapshot, standard set, and scope.
Human mappings are used only after model stages, for disagreement inspection.
Their imported levels are not ground truth and pair overlap is not accuracy.

The default produces raw input preparation and a review artifact. It reports
**prepared_only**, with no fabricated synthesis or new alignment outcomes.

## Live pilot and incremental reuse

Set `ANTHROPIC_API_KEY` in the environment or ignored `service/.env`. Supply a
model ID available to that account; no model ID or pricing is guessed.

```bash
python service/standards_pipeline.py --baseline-run 3 --human-run 8 \
  --live --model YOUR_MODEL_ID --limit 5 --out runs/v2-pilot
```

Use repeated `--lesson 'unit::Exact lesson name'` arguments to select a targeted
pilot. `--limit` limits lesson synthesis, not the denominator for course coverage.
Unprocessed lessons remain unknown. Unit synthesis and review explicitly refer to
available lessons; they do not assert complete-unit results for an incomplete pilot.

Stages can be run separately:

```bash
# Reusable corpus layer, without any standards interpretation or alignment calls.
python service/standards_pipeline.py --baseline-run 3 --stage inventory \
  --live --model YOUR_MODEL_ID --out runs/v2-inventory

# Or directly from the GitHub-extracted corpus, without a database.
python service/standards_pipeline.py --corpus corpus --stage inventory \
  --live --model YOUR_MODEL_ID --out runs/v2-corpus-inventory

# Required-performance interpretation only.
python service/standards_pipeline.py --baseline-run 3 --stage performances \
  --live --model YOUR_MODEL_ID --out runs/v2-performances

# Full course, reusing identical cached stages and reviewed interpretation files.
python service/standards_pipeline.py --baseline-run 3 --human-run 8 \
  --performances runs/v2-performances/performances.json \
  --live --model YOUR_MODEL_ID --out runs/v2-full
```

Cache entries include the model, prompt, schema and exact stage inputs, and are
revalidated when reused. Inventory and unit-sequence keys contain no standards
framework, so they can be reused across states. Changed content, course route
conditions, or extraction metadata can invalidate affected entries. Paid calls
stop after `--max-failures` (default 3). Progress and API-reported token usage are
checkpointed. Dollar cost remains unset rather than using stale prices.

`--replay-cache --model YOUR_MODEL_ID` reruns only cached stages, with no API
calls. Missing cache entries are explicit incomplete-stage failures. Use a fresh
output folder for every run; shared cache defaults to `runs/standards-v2-cache`.

## Review and persistence

Each run creates a standalone `report.html`, `report.json`, `sources.json`,
`inventory.json`, `performances.json`, and (when processing) checkpoint/usage files.
Open the HTML directly or load the JSON in
`tools/standards-mapper/evidence.html`.

The review surface shows:

- Historical baseline/human pair overlap, without treating it as accuracy.
- Course and unit requirement coverage, assessment evidence, and uncertainty.
- Unit instructional sequences linked to lesson evidence.
- Every synthesized item with exact quotes and pathway conditions.
- Missing resources, processing failures, and source/model provenance.

For internal database-backed review, apply the additive migration explicitly:

```bash
python service/db/migrate_evidence.py --dry-run
python service/db/migrate_evidence.py
```

New installations include these tables in generated `schema.sql`. The migration
is idempotent and preserves legacy data. Add `--persist` to save a proposed v2
artifact and versioned inventories/interpretations. Do not use a production
connection for tests or fixture loading.

`GET /api/evidence-runs` lists saved artifacts. `GET /api/evidence-runs/{id}`
returns one artifact and its review history. `POST .../{id}/reviews` records an
accept/reject/needs-review decision on a course or unit standard outcome, requiring
its matching input fingerprint, reviewer, and reason. The workbench exposes this
flow only after loading a saved artifact. Decisions do not overwrite findings or
publish results; the legacy public API remains unchanged. A regenerated artifact
requires its own reviews. Reviewer identity follows the existing prototype's
self-reported actor model, not a new authentication system.

## Reading coverage

- `full`: every required component is fully evidenced across paths, with any
  required integration witness.
- `components_only`: components are present, but the required integrated
  performance has not been established.
- `partial`: some required performance is shared, but coverage is incomplete.
- `conditional`: performance is available only on some paths.
- `exposure_only` / `supporting_only`: valid instructional contributions without
  evidence of the required performance.
- `none_observed`: available evidence was fully processed and no connection found.
- `unknown`: processing or relevant source availability prevents a negative conclusion.

Evidence sufficiency is independent. Missing linked materials and unclear
inventory passages prevent confident negative judgments; known positives remain.
An assessment-at-expected-demand finding is about curriculum tasks, not measured
student attainment. Human review can disagree with a proposed model finding.

## Baseline repairs

The original `align.py` now passes its defined standards text, honors its evidence
mode, executes its optional tier-1 screen, and stops without writing course-gap
outcomes if any lesson fails. Existing historical runs are untouched. Its old
rating scheme still differs from v2; do not compare rating labels as equivalent.
Legacy pilot/screened results are not evidence of whole-course absence.

## Tests

```bash
python service/test_standards_v2.py
python service/test_alignment_evidence.py
python service/test_alignment.py
python service/test_curriculum.py
python service/db/build_schema.py --check
```

The new tests include live-call stubs plus free cache replay through the complete
CLI, recovery of a discovery miss by unit review, source accounting, exact quotes,
equivalent/nested/bonus choices, complementary units, mutually exclusive evidence,
integration witnesses, assessment constraints, failure handling, stale review
rejection, and preservation of the baseline runner. Stub tests do not establish
semantic precision or recall. Real model comparisons still require credentials
and educator adjudication of a balanced disagreement sample.
