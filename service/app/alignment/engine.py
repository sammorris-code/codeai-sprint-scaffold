"""The candidate set, the prompt, and the one model call per lesson.

**One lesson at a time.** A lesson is a few thousand tokens; the standards set
is much larger and identical for every lesson in a run. So the standards go in
the cached prefix and the lesson is the only thing that changes, which is what
makes a 148-lesson run cost single-digit dollars instead of hundreds.

**The model is asked for its rejections too.** A claim it did not make is
invisible otherwise, and the briefing wants a rejection log with a specific
reason per rejection — partly so a reviewer can see what a naive keyword match
would have wrongly claimed, and partly because a rejection resting on a drafted
boundary may be the boundary's fault rather than the curriculum's.
"""
import json
import os
import pathlib
import re

MODEL = os.environ.get("ALIGNMENT_MODEL", "claude-opus-5")

# Bands are compared by the grades they cover, never as strings. A state says
# "9-10" and "11-12" where CSTA says "9-12"; comparing the labels matches
# nothing and would silently empty the candidate set.
GRADE_WORDS = {"PK": -1, "K": 0, "PRE-K": -1}


def grades_in(band):
    """The set of grades a band label covers."""
    if not band:
        return set()
    text = str(band).upper().replace("GRADE", "").replace("S", "").strip()
    out = set()
    for part in re.split(r"[,/]", text):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^([A-Z0-9\-]+?)\s*[-–]\s*([A-Z0-9]+)$", part)
        if match:
            lo, hi = match.group(1), match.group(2)
            lo_n = GRADE_WORDS.get(lo, None)
            hi_n = GRADE_WORDS.get(hi, None)
            try:
                lo_n = int(lo) if lo_n is None else lo_n
                hi_n = int(hi) if hi_n is None else hi_n
            except ValueError:
                continue
            out.update(range(min(lo_n, hi_n), max(lo_n, hi_n) + 1))
        else:
            n = GRADE_WORDS.get(part)
            if n is None:
                try:
                    n = int(part)
                except ValueError:
                    continue
            out.add(n)
    return out


def candidate_standards(standards, course_grades=None):
    """Which standards this course could plausibly be judged against.

    Filtering is by grade band only, and only when the course states one. The
    skill is explicit that the default candidate set is the whole framework: a
    Programming unit showing most Society standards as not addressed is useful
    information, not a problem to filter away.
    """
    if not course_grades:
        return list(standards), {"filtered": False, "kept": len(standards)}
    wanted = grades_in(course_grades)
    kept = [s for s in standards
            if not s.get("grade_band")
            or not grades_in(s["grade_band"])
            or grades_in(s["grade_band"]) & wanted]
    return kept, {"filtered": True, "kept": len(kept),
                  "dropped": len(standards) - len(kept)}


RULES = """You judge whether a curriculum lesson addresses a standard, and at \
what level. You are producing evidence a school district will read, so a claim \
you cannot point at is worse than no claim.

Rate each standard you claim at one of three levels:

- introduced — the concept appears as exposure only. A mention, a definition, a \
brief example. Students produce no evidence of the skill.
- developed — students work with the concept across activities, with practice \
and feedback, but there is no summative assessment of it.
- mastered — students produce observable evidence at the cognitive level the \
standard demands, with opportunity for feedback and revision.

A standard you do not claim is not addressed by this lesson. Say why in \
`considered_and_rejected` whenever the lesson is topically close enough that a \
keyword match would have claimed it.

Rules that decide a claim:

1. Evidence is a specific student task — an activity, a prompt, a level. "The \
lesson is about this topic" is not evidence. A word appearing in both is not \
evidence. If you cannot name the task, do not claim the standard.
2. Read boundary_includes and boundary_excludes before claiming. If the \
evidence matches an exclusion, reject it and say which exclusion.
3. The cognitive verb of the standard is the ceiling. A standard that says \
"evaluate" or "design" is not mastered by a multiple-choice question. Set \
cognitive_verb_match false when the student task sits below the standard's verb.
4. If the standard names an artifact — a program, a dataset, documentation — \
and the lesson produces a different kind of artifact, set artifact_match false \
and say so in the note.
5. A claim whose evidence sits only in a choice branch is met by a fraction of \
the class. Set is_choice_level true, name the option, and rate it introduced.
6. One to three standards per lesson is normal. If you find yourself claiming \
six or more, most of them are exposure at best. Be honest about that.
7. Do not claim what the lesson could cover. Claim what it does.

The curriculum is locked. You are observing it, not improving it. Never \
suggest changes or describe a gap as something to close."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "standard_id": {"type": "string"},
                    "level": {"type": "string",
                              "enum": ["introduced", "developed", "mastered"]},
                    "evidence": {"type": "string"},
                    "cognitive_verb_match": {"type": "boolean"},
                    "artifact_match": {"type": "boolean"},
                    "is_choice_level": {"type": "boolean"},
                    "choice_option": {"type": ["string", "null"]},
                    "note": {"type": ["string", "null"]},
                },
                "required": ["standard_id", "level", "evidence",
                             "cognitive_verb_match", "artifact_match",
                             "is_choice_level", "choice_option", "note"],
                "additionalProperties": False,
            },
        },
        "considered_and_rejected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "standard_id": {"type": "string"},
                    "kind": {"type": "string",
                             "enum": ["boundary_exclusion", "no_evidence",
                                      "verb_mismatch", "artifact_mismatch",
                                      "topical_only"]},
                    "reason": {"type": "string"},
                },
                "required": ["standard_id", "kind", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims", "considered_and_rejected"],
    "additionalProperties": False,
}


def standards_block(standards):
    """The candidate set, rendered once and cached.

    Identical for every lesson in a run, so it is written to the cache on the
    first call and read cheaply by all the rest.
    """
    lines = ["The standards you are judging against:", ""]
    for s in standards:
        lines.append(f"## {s['identifier']}")
        lines.append(f"Concept: {s['concept']}"
                     + (f" · {s['subconcept']}" if s.get("subconcept") else "")
                     + (f" · grades {s['grade_band']}" if s.get("grade_band") else ""))
        lines.append(f"Statement: {s['statement']}")
        if s.get("boundary_includes"):
            lines.append("Counts as addressing it:")
            lines += [f"  - {x}" for x in s["boundary_includes"]]
        if s.get("boundary_excludes"):
            lines.append("Does NOT count, despite overlap:")
            lines += [f"  - {x}" for x in s["boundary_excludes"]]
        if s.get("keywords"):
            lines.append("Retrieval terms (never sufficient evidence): "
                         + ", ".join(s["keywords"][:12]))
        if s.get("boundary_provenance") == "drafted":
            lines.append("NOTE: these boundaries were drafted during ingestion "
                         "and no person has checked them. If you reject this "
                         "standard on a boundary, say so — the boundary may be "
                         "what is wrong, not the curriculum.")
        lines.append("")
    return "\n".join(lines)


def lesson_block(lesson, distilled):
    """The one thing that changes per call."""
    plan = lesson.get("plan") or {}
    out = [f"# {lesson['lesson_name']}",
           f"Unit: {lesson['unit_name']} (`{lesson['script_name']}`)",
           f"Lesson {lesson['relative_position']} of the unit.",
           f"Stable id: {lesson['stable_id']}"]
    if lesson.get("lesson_group_name"):
        out.append(f"Group: {lesson['lesson_group_name']}")
    if distilled.get("is_alternate_progression"):
        out.append("This is an ALTERNATE progression: a second version of a "
                   "lesson the unit teaches elsewhere. A student does one or "
                   "the other.")
    out.append("")

    objectives = plan.get("objectives") or []
    out.append("## Objectives the authors wrote")
    out += ([f"- {o}" for o in objectives] if objectives
            else ["(none authored — there is nothing here to anchor a claim on)"])
    out.append("")

    out.append("## What students actually do")
    out.append("Taken from the student screens, in the order a student meets "
               "them. This is the evidence; the prose above is intent.")
    for action in distilled.get("every_student", []):
        out.append(f"- {action['action']} — `{action['level']}` "
                   f"({action['level_type']})")
        for step in action.get("steps", [])[:5]:
            out.append(f"    - {step}")
    if not distilled.get("every_student"):
        out.append("- (nothing outside a choice branch)")
    out.append("")

    optional = distilled.get("one_option_only", [])
    if optional:
        out.append("## What only some students do")
        out.append("Each student completes ONE of these. A claim resting on "
                   "one is met by a fraction of the class — cap it at "
                   "introduced and name the option.")
        for action in optional:
            out.append(f"- {action['action']} — `{action['level']}` "
                       f"(option of `{action['choice_parent']}`)")
        out.append("")

    if distilled.get("produces"):
        out.append("## What students produce")
        out += [f"- {p['artifact']} — `{p['level']}`"
                for p in distilled["produces"]]
        out.append("")
    if distilled.get("checked"):
        out.append("## What is checked")
        out += [f"- `{c['level']}` — {c['how']}" for c in distilled["checked"]]
        out.append("")

    authorship = distilled.get("authorship") or {}
    if any(authorship.get(k) for k in ("student_authored", "student_specified",
                                       "outcome_prompted")):
        out.append("## Who writes the code")
        out.append(f"- student typed or edited it: "
                   f"{authorship.get('student_authored', 0)} levels")
        out.append(f"- student wrote the algorithm and directed a model from "
                   f"it: {authorship.get('student_specified', 0)} levels")
        out.append(f"- student asked a model for an outcome without "
                   f"specifying the logic: "
                   f"{authorship.get('outcome_prompted', 0)} levels")
        out.append("Our policy counts the first two as the student writing "
                   "the code. The third is not writing.")
        out.append("")

    if plan.get("overview_md"):
        out.append("## The teacher's overview, for context only")
        out.append(str(plan["overview_md"])[:1500])
        out.append("")
    return "\n".join(out)


def load_key(env_path="service/.env"):
    """Read ANTHROPIC_API_KEY from the environment, or from service/.env."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    path = pathlib.Path(env_path)
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
            return True
    return False


def judge(client, standards_text, lesson, distilled, model=MODEL, usage=None):
    """One lesson against the cached standards. Returns the parsed answer."""
    import anthropic  # imported here so the module loads without the SDK

    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=[
            {"type": "text", "text": RULES},
            # The breakpoint goes after the standards, which are identical for
            # every lesson in the run. The lesson itself is in `messages`,
            # after it, so it never invalidates the prefix.
            {"type": "text", "text": standards_text,
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user",
                   "content": lesson_block(lesson, distilled)}],
        output_config={"format": {"type": "json_schema",
                                  "schema": ANSWER_SCHEMA}},
    )
    if usage is not None:
        u = response.usage
        usage["calls"] = usage.get("calls", 0) + 1
        for field in ("input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens"):
            usage[field] = usage.get(field, 0) + (getattr(u, field, 0) or 0)

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


# Opus 5, dollars per million tokens. Cache reads are a tenth of input.
PRICES = {"claude-opus-5": (5.0, 25.0, 6.25, 0.50),
          "claude-sonnet-5": (2.0, 10.0, 2.50, 0.20),
          "claude-haiku-4-5": (1.0, 5.0, 1.25, 0.10)}


def cost_of(usage, model=MODEL):
    inp, out, cache_write, cache_read = PRICES.get(model, PRICES["claude-opus-5"])
    return (usage.get("input_tokens", 0) * inp
            + usage.get("output_tokens", 0) * out
            + usage.get("cache_creation_input_tokens", 0) * cache_write
            + usage.get("cache_read_input_tokens", 0) * cache_read) / 1_000_000
