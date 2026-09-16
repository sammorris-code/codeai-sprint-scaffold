# Where review happens, and why it moved

Status: decided, not yet built. This note reverses a rule `tables.md` currently
states. Read it before changing anything about review.

## What this replaces

The set-level boundary gate. Today a standards set is unpublishable until a
person has given every one of its boundaries a verdict, and the publish query in
`tables.md` requires `boundary_provenance = 'drafted+reviewed'` on the whole set.

That rule is being removed. What follows is what replaces it.

## Why the old rule was wrong

Two reasons, and the second is the one that matters.

**It did not scale, by a factor nobody would pay.** Twenty-five states at roughly
seventy standards each is about 1,750 boundaries. At half a minute each that is
some fifteen hours of an expert's attention, spent before a single alignment has
been run.

**A boundary read on its own cannot be judged.** This is the real problem.
Handed the line *"excludes: a lesson that only mentions loops"* with nothing else
in front of you, there is no way to say whether it is right. You are proofreading
a hypothesis. The reviewer has no lesson to hold it against, so the verdict is a
guess wearing the costume of a check — and it is that appearance of rigour, not
the wasted hours, that makes the old gate worse than no gate at all.

Most of those 1,750 boundaries would never have decided anything either. A
boundary only does work when a lesson is claimed against it. Reviewing the rest
is effort spent on questions nobody asked.

We also already knew better. The earlier California CTE ICT run gated review to
about 197 rows out of 322 — scoped to what actually carried a claim. The gate in
`tables.md` was stricter than the workflow that had already been proven to work.

## The rule that replaces it

**Ingest freely. Review where an alignment makes a boundary matter.**

A set is publishable on ingestion. Its boundaries are honest drafts, marked
`drafted`, and nothing pretends otherwise. Review is triggered by an alignment,
carries the alignment with it, and is the only kind of review anyone is asked to
do.

The reviewer is never shown a boundary alone. They are shown a lesson, a
standard, and the boundary that stood between them, and they may fix either
side — widen the boundary, or drop the claim. That is a decision a person can
actually make, in seconds, because the example is right there.

## What triggers a review

Two signals. They are not equal, and the difference is deliberate.

### 1. The boundary rejected a claim — a queue item

The engine found evidence it believed in, and an exclusion blocked it. This
announces itself: a rejection is the signal, no extra machinery needed.

It is also the higher-value case. A drafted boundary written from the statement
alone, with no clarifying text to work from, is drawn narrow on purpose. Narrow
is the right default and it is also the one that will be wrong most often. The
Texas run is the record: *twelve of the boundary rejections would have converted
to coverage if a reviewer had widened the drafted boundaries.*

Volume is small. Texas CS I: 4 boundary issues across 62 standards. CS II: 8
across 59. Roughly a tenth of a set, not all of it.

### 2. The evidence behind a claim is thin — a flag, not a gate

A claim went through, but what it rests on is weak: a short quote, a keyword
match, evidence that does not survive the same kind of check `analogs.py` applies
to a claimed CSTA analog.

**This is surfaced, and it does not block anything.** That is a deliberate
correction to an earlier draft of this design, which treated a stretched
alignment as something close to a defect.

It is not. Standards are written vague, and a lesson rarely satisfies one
cleanly. Partial coverage is the ordinary case in this work, and a teacher
adding to a lesson so a student reaches the standard is the system working as
intended — not a failure being papered over. Districts expect this. Building a
gate on the assumption that every stretch is a harm would stop real work to
prevent something the field already handles.

So the flag exists to improve quality where someone has attention to spare, not
to hold a release. The distinction still worth keeping: a lesson that partly
covers a standard is normal and useful; a claim of coverage where there is no
evidence at all is a different thing, and that is what the evidence check catches
mechanically, without anyone's judgement.

## What code checks, and what it cannot

Follow what the analog gate did. `nearest_csta` used to hold bare identifiers —
an assertion nothing could test — so the drafter now quotes the CSTA wording it
adapted, and code checks the quote is real. Ask alignment for the same thing.

**Checkable in code, free, on every row:** an alignment quotes the lesson text it
relies on, and that quote must genuinely appear in that lesson. Anything else is
a claim with nothing behind it, and it never reaches a person.

**Not checkable:** whether the quoted text actually satisfies the standard. That
is judgement, and it is the only thing a person should be asked for — one row, in
context, with the evidence attached.

## What changes in the contract

- `boundary_provenance` stops being a publish gate. It stays as a record of where
  a boundary came from, which is still worth knowing.
- The publish query in `tables.md` drops its `drafted+reviewed` condition. An
  approved run is the remaining condition.
- `drafted+reviewed` keeps its meaning — a person checked this boundary against a
  real alignment — but it becomes an outcome of review, not a precondition for
  publishing.
- Review events move to the alignment record. `review_event` already carries both
  a `standard_id` and a `record_id`, so the table does not change.
- Nothing about ingestion changes. Sets arrive as they do now.

## What not to build

A review interface for boundaries in bulk. There is no version of that screen
worth building, because there is no version of that question worth asking.
