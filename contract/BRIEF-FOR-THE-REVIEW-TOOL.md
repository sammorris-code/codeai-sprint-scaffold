# What changed, and what the review tool has to become

For whoever picks the review tool back up. The bottom of this file is a prompt
you can hand to Claude Code as-is.

## The short version

The review tool you built works. The rule it was built around does not exist any
more. Nothing you wrote was wrong — the thing it was checking turned out to be
the wrong thing to check.

## What the old rule was

A standards set could not publish until a person had given a verdict on every
boundary in it. The tool showed that: a lock banner, a disabled publish button,
a queue that counted down to zero.

## Why it went

Two reasons. The second is the real one.

It did not scale. Twenty-five more states is roughly 1,750 boundaries to sit and
check before a single alignment has run.

And a boundary read on its own cannot be judged. Given the line *"excludes: a
lesson that only mentions loops"* with nothing else in front of you, there is no
way to say whether it is right. You would be proofreading a hypothesis, and the
verdict would be a guess that looks like a check. That appearance of rigour is
worse than no check at all.

`contract/REVIEW-DESIGN.md` is the full note.

## The rule now

**Publishing needs an approved run. That is the whole condition.**

Sets arrive publishable. Their boundaries are honest drafts. Review is triggered
by an alignment and always carries that alignment with it, so the reviewer sees a
lesson, a standard, and the boundary between them — and can fix either side.

Two triggers, deliberately unequal:

- **The boundary rejected a claim.** A queue item. The engine found evidence it
  believed in and an exclusion blocked it. This is where drafted-narrow
  boundaries are most often wrong, and it is a small pile: one earlier run had 4
  such cases in 62 standards, another 8 in 59.
- **The evidence behind a claim is thin.** A flag. It blocks nothing. Standards
  are written vague, a lesson rarely satisfies one cleanly, and a teacher adding
  to a lesson so a student reaches the standard is the system working. This is
  worth surfacing, not worth stopping anyone over.

## What is already changed in the repo

- `publishable` on a standards set is now **`all_boundaries_checked`**. Same
  computation, honest name: it reports whether a person has checked every
  boundary, and it no longer decides anything.
- `/api/runs/{id}/approve` no longer refuses when the boundaries are unchecked.
- The public endpoints no longer filter on the set's boundary state.
- The boundary queue and verdict endpoints still exist and still work. They are
  now a worklist, not a gate.
- In `queue.js`, the banner and button copy no longer claim the removed rule. The
  publish button is still tied to `all_boundaries_checked`, which is **not** the
  real rule — left that way on purpose, because it shows less rather than more,
  and rewiring it belongs in the rebuild.

## What the tool has to become

The centre of the screen changes. It stops being *a set's boundaries* and becomes
*an alignment and the boundary it turned on*. The reviewer needs the lesson, the
standard, the boundary, and two ways out: widen the boundary, or drop the claim.

Sam has a post-alignment prototype built elsewhere that is closer to this than
the current tool. Find it before rebuilding from scratch.

---

## Prompt to hand to Claude Code

> I'm picking up the standards review tool in `tools/standards-mapper/`. Before
> changing anything, read `contract/REVIEW-DESIGN.md`, then
> `contract/BRIEF-FOR-THE-REVIEW-TOOL.md`, then `contract/api.md`.
>
> The rule the tool was built around is gone. It used to be that a standards set
> could not publish until every boundary in it had a human verdict. Now
> publishing needs only an approved run, and boundaries get reviewed when an
> alignment turns on one — with the lesson and the standard in front of the
> reviewer, who can widen the boundary or drop the claim.
>
> Tell me what in the current tool survives that change and what does not, before
> writing any code. I especially want to know which screens are still asking a
> question worth asking. Two I already suspect are not: the lock banner in
> `queue.js`, and the unchecked-set count in `mapper.js`.
>
> Note that `publishable` was renamed to `all_boundaries_checked` across the
> contract and the service. The field still computes the same thing; it just no
> longer gates anything.
>
> Two constraints that have not changed. Every path stays relative — a
> root-absolute path escapes the `pr-preview/pr-<number>/` folder and silently
> loads the live site's file instead. And anything interactive has to be reachable
> by tab and operable by keyboard; these are school districts.
>
> One thing to confirm with me before you build: there is a post-alignment
> prototype that is closer to the new shape than the current tool. Ask me for it
> rather than designing the screen from scratch.
