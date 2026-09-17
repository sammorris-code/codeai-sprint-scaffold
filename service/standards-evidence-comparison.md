# Standards evidence comparison

This opt-in pipeline compares source-grounded judgments with an existing run.
The original `align.py`, ingestion service, database schema, API, and review UI
are unchanged. The comparison reads the store and writes local reports only.
It cannot approve or publish a run.

## What changes

| Existing pipeline | Comparison pipeline |
| --- | --- |
| Truncated teacher-plan and student-screen excerpts | Complete, addressable source passages, including teacher-led tasks and assessment tips |
| Level-type action summary | Authored source text; an editor type alone proves no performance |
| Inherited standards tags in the corpus | Tags excluded from model evidence |
| Drafted boundaries can determine rejection | State statement controls; boundaries and CSTA IDs are advisory |
| One lesson rating for a whole standard | Findings for each proposed requirement, including explicit rejections |
| Lower one level for a verb mismatch | Distinguish full, partial, prerequisite, exposure, and absent evidence |
| Choice claims capped at introduced | Preserve their actual depth, but separate them from shared coverage |
| Highest lesson rating becomes course outcome | Combine fully supported requirements; repeated partial evidence never becomes full |
| Boundary issue competes with coverage | Boundary review and evidence sufficiency coexist with coverage |
| Mastered | Explicit independent performance and assessment evidence; no student mastery claim |
| Failed or omitted lessons can resemble gaps | Unprocessed lessons and invalid evidence keep course conclusions incomplete |

Exact quotation checks establish source integrity, **not semantic correctness**.
The model still interprets whether a quoted task addresses a requirement, whether
it is independent work, and whether assessment criteria apply. All findings and
requirement decompositions remain proposed for human review.

## Inputs

Use a local, isolated restore of your PostgreSQL dump. Set `DATABASE_URL` to it.
All queries run in one repeatable-read, read-only transaction. The selected
baseline run supplies the snapshot and standard-set identity; the tool does not
switch to the course's latest snapshot. Scope comes from the baseline's stored
`standard_outcome.in_scope` rows. If no outcomes exist, the report explicitly
labels the whole-set fallback. It never interprets scope prose as a filter.

Alternatively, export the same tables for offline use:

```bash
python service/compare_standards.py --list-runs --export-dataset runs/local-dataset.json
```

Use `--dataset runs/local-dataset.json` in subsequent commands to avoid a database
connection. Keep dumps, exports, reports, and API credentials out of Git.

## Audit first: no model or key required

```bash
python service/compare_standards.py --baseline-run 3 --out runs/evidence-audit
```

Open `runs/evidence-audit/comparison.html`. It contains the preserved baseline
claims and a source audit. The new alignment column says **not run**. No coverage
improvement or semantic correction is claimed by an audit.

Audit counts of passages over 900 characters identify where the existing prompt
builder clips text; they do not prove relevant evidence was lost. Missing linked
resources also indicate uncertainty, not a demonstrated curricular gap.

## Live pilot

Configure `ANTHROPIC_API_KEY` in the environment or the existing ignored
`service/.env`. Pass a model ID available to your account explicitly:

```bash
python service/compare_standards.py --baseline-run 3 --limit 5 \
  --live --model YOUR_MODEL_ID --out runs/evidence-pilot
```

The tool first proposes state-text requirements in batches of ten, then makes
one alignment call per selected lesson. It does not filter lesson/standard pairs
lexically. Standards stay in a cached prefix. Token usage is recorded from API
responses; dollar cost remains unset rather than relying on a stale price table.
The default stop threshold is three failed lessons (`--max-failures`). Failed
and unselected lessons remain unprocessed in course aggregation.

Use repeated `--lesson 'exact::stable ID'` arguments for a controlled sample.
Use `--whole-statements` to keep one requirement per standard instead of asking
the model to decompose it. Use `--requirements runs/evidence-pilot/requirements.json`
to reuse a decomposition for a subsequent run. Requirement quotes must be exact
substrings and collectively cover every alphanumeric character of the original
statement; this detects omissions but cannot prove a sound interpretation.
Every fragment is evaluated in the context of the complete standard.

After reviewing the pilot, omit `--limit` for the full course. Use a fresh output
directory; the command refuses to overwrite previous evidence.

## Read the outputs

- `comparison.html`: self-contained baseline/new outcome table, expandable claims,
  exact quotations, verification problems, and boundary-review reasons.
- `comparison.json`: machine-readable baseline, verified findings, outcomes,
  audit, manifest, and failures.
- `evidence.json`: source text and JSON-pointer locations, pathway metadata,
  resource gaps, and content fingerprints. Nothing is truncated.
- `requirements.json`: proposed source-grounded requirements.
- `answers.json`: raw model answers, saved after every lesson, plus input fingerprint.
- `manifest.json`: snapshot, standard-set metadata, scope, model, code fingerprint,
  baseline fingerprint, and selected lessons.
- `usage.json`: API-reported tokens and call counts, including completed calls
  whose output later fails validation.

For a full audit trail, keep the entire directory. Replay saved answers without
paid calls:

```bash
python service/compare_standards.py --baseline-run 3 \
  --requirements runs/evidence-pilot/requirements.json \
  --replay runs/evidence-pilot/answers.json --out runs/evidence-replay
```

Replay refuses changed sources, standards interpretations, boundaries, or pipeline
code. Historical baseline records remain preserved even if they were generated
by an older model or prompt; this is not a controlled model A/B experiment unless
you also rerun the baseline on the same snapshot and model.

## Aggregation and limitations

Shared coverage is full only when every required component has at least one
source-verified full-performance finding on a shared pathway. Partial findings
never add up to full. Choice, bonus, and alternate evidence retain depth in their
lesson findings, but do not count as shared coverage. The first version does not
prove that **all** alternatives satisfy the same requirement; a reviewer must
resolve that conservative limitation.

Assessment at expected demand requires all components to have full independent
performance and cited shared assessment evidence. It is a property of the
curriculum's tasks, never a conclusion about student attainment. Highest supported
depth is reported separately and is not itself a whole-standard coverage rating.

Missing resources or processing failures mark evidence sufficiency incomplete.
Supported positives remain visible; `none_observed` with incomplete evidence is
not a claim that the curriculum omits the standard. Since relevance of unseen
resources cannot be established, their presence conservatively marks every
candidate's evidence incomplete. Source documents are not fetched automatically.

This branch adds a separate interpretation layer rather than rewriting existing
ingested boundaries. It does not yet add database persistence or a production
approval flow for the new outcome dimensions. Existing approved runs are intact.
After comparison, adopting these dimensions in the main app requires a reviewed
schema/API/UI migration; do not coerce them into the legacy `level` column.

## Verification

```bash
python service/test_alignment_evidence.py
python service/test_alignment.py
```

Tests use synthetic curriculum and stubbed model responses. They cover lost-tail
evidence, optional readings, missing resources, intent-only citations, fabricated
quotes, missing/duplicate candidates, requirement omissions, complementary course
coverage, repeated partial work, optional-path contamination, assessment citations,
failure handling, independent review status, and fingerprint-checked replay.
They do not measure semantic precision or recall against educator judgments.
