"""The distilled layer: what a student actually does in a lesson.

The reason is signal, not size. A lesson plan is mostly teacher choreography —
"Review the lesson objectives", "Direct students to Stand and Swap" — which a
teacher needs and an alignment reviewer cannot use. The authored objectives are
too general to say what a student produces. Alignment is rated on one thing:
the observable student action, at the cognitive verb the standard demands. This
converts a lesson into that.

**The primary signal is the level type, not a heading.** The first design read
student actions from "Do This" headings. Measured across all 147 taught AIF
lessons, that heading appears in only 70% of them, and the lessons it misses
hold a quarter of all student words. The level type reaches 99%:

    signal                        lessons reached   student words missed
    "Do This" only                    70%                  24.8%
    + "Directions:"                   71%                  22.8%
    + numbered steps                  84%                   7.5%
    + imperative heading              85%                   6.8%
    + the level type                  99%                   0.6%

That is not only a bigger number. A heading is a writing convention and an
author can change it without telling anyone. A level type is authored metadata:
a `pythonlab` level means the student writes Python whatever the prose says.
Prose markers are still read, but to say *what* the student does inside a level
the type has already proved is active.

**This layer is derived. It must never replace the corpus.** It is rebuilt
whenever the corpus is, so it cannot go stale on its own — which is why the
extractor always writes it rather than offering a flag somebody forgets.

**It concludes nothing.** Where it cannot tell, it asks, and the question goes
in `open_questions` for a person.
"""
import re

from .levels import strip_markup

# What a level type means a student does. This is the primary signal.
#
#   action    - the observable thing, in the student's own terms
#   produces  - the student leaves an artifact behind
#   code      - the artifact is code, which matters for the authorship question
TYPE_ACTIONS = {
    "freeresponse":     ("writes a written response", True, False),
    "aichat":           ("prompts an AI model and reads what it returns", True, False),
    "weblab2":          ("edits HTML, CSS or JavaScript in an editor", True, True),
    "weblab":           ("edits HTML, CSS or JavaScript in an editor", True, True),
    "pythonlab":        ("writes Python", True, True),
    "applab":           ("writes an app in App Lab", True, True),
    "gamelab":          ("writes a program in Game Lab", True, True),
    "javalab":          ("writes Java", True, True),
    "sketchlab":        ("draws or diagrams", True, False),
    "multi":            ("answers a multiple-choice question", False, False),
    "evaluation_multi": ("answers a multiple-choice question", False, False),
    "match":            ("matches items to each other", False, False),
    "text_match":       ("writes a short answer", True, False),
    "contract_match":   ("matches items to each other", False, False),
    "bubble_choice":    ("chooses one option to work through", False, False),
    "level_group":      ("works through a group of screens", False, False),
    "craft":            ("builds something in Craft", True, True),
    "dancelab":         ("writes a program in Dance Lab", True, True),
    "netsim":           ("uses the internet simulator", False, False),
}

# Types where the student reads or watches. Real, and not an action that
# evidences a standard on its own.
READING_TYPES = {"panels", "external", "externallink", "standalone_video",
                 "video", "unplugged", "markdownlevel"}

# Prose markers, in the order they are trusted. These refine an action; they
# never establish one.
MARKERS = [
    ("do_this",     re.compile(r"#{0,4}\s*\**\s*do\s*this\s*:?\s*\**", re.I)),
    ("directions",  re.compile(r"#{0,4}\s*\**\s*directions\s*:?\s*\**", re.I)),
    ("numbered",    re.compile(r"^\s*\d+\.\s+\S", re.M)),
    ("imperative",  re.compile(
        r"^#{1,4}\s*(Write|Build|Create|Make|Add|Fix|Plan|Code|Draw|Choose|"
        r"Pick|Predict|Compare|Record|Describe|Explain|Analyze|Test)\b", re.M | re.I)),
]

# A step, as authored: a numbered line or a bullet under a marker.
STEP = re.compile(r"^\s*(?:\d+\.|[-*])\s+(.{6,300}?)\s*$", re.M)

BLOOM = ("analyze", "evaluate", "create", "apply", "understand", "remember",
         "explain", "describe", "compare", "identify", "implement", "design",
         "develop", "build", "write", "test", "debug", "predict", "model")

# The student told the model to write the code, rather than writing it.
AI_WROTE = re.compile(
    r"\b(ask|prompt|tell)\s+(the\s+)?(ai|assistant|chatbot|model)\b"
    r"|\bhave\s+(the\s+)?ai\s+(write|generate|create)\b"
    r"|\bgenerate[sd]?\s+(the\s+)?code\b", re.I)
STUDENT_WROTE = re.compile(
    r"\b(write|edit|change|fix|add|type)\b[^.]{0,40}\b(code|function|line|"
    r"statement|program|loop|conditional)\b", re.I)

ALTERNATE_GROUP = re.compile(r"alternate", re.I)


def _steps(text):
    """The authored steps in a level, as written. Never reworded."""
    out = []
    for match in STEP.finditer(text or ""):
        step = strip_markup(match.group(1)).strip()
        if len(step) >= 6:
            out.append(step)
    return out[:12]


def _markers_in(text):
    return [name for name, rx in MARKERS if rx.search(text or "")]


def distil(lesson):
    """One distilled record from one lesson record."""
    group = lesson.get("lesson_group_name") or ""
    is_alternate = bool(ALTERNATE_GROUP.search(group))

    actions, choice_points, produces, checked = [], [], [], []
    signals = {"level_type": 0, "do_this": 0, "directions": 0,
               "numbered": 0, "imperative": 0}
    code_by_student = code_by_ai = 0
    reading_levels = 0

    for level in lesson.get("levels") or []:
        level_type = str(level.get("level_type") or "").lower()
        context = level.get("context") or {}
        text = level.get("student_text") or ""

        if level_type in READING_TYPES:
            reading_levels += 1
            continue

        known = TYPE_ACTIONS.get(level_type)
        if not known:
            # Unknown type. Do not guess it is inactive; ask.
            known = (f"works in a `{level_type}` level", False, False)

        action_text, makes_artifact, is_code = known
        found = _markers_in(text)
        for name in found:
            signals[name] += 1
        signals["level_type"] += 1

        if is_code:
            if AI_WROTE.search(text):
                code_by_ai += 1
            elif STUDENT_WROTE.search(text) or not AI_WROTE.search(text):
                code_by_student += 1

        entry = {
            "level": level.get("level_name"),
            "level_type": level_type,
            "action": action_text,
            "steps": _steps(text),
            "prose_markers": found,
            "is_choice_option": bool(context.get("is_choice_option")),
            "choice_parent": context.get("choice_parent"),
            "is_assessment": bool(context.get("is_assessment")),
            "is_bonus": bool(context.get("is_bonus")),
            "word_count": level.get("word_count", 0),
        }
        actions.append(entry)

        if makes_artifact and not entry["is_choice_option"]:
            produces.append({"level": entry["level"], "artifact": action_text})
        if level.get("has_validation") or entry["is_assessment"]:
            checked.append({"level": entry["level"],
                            "how": "validated by the level"
                            if level.get("has_validation") else "marked as assessment"})
        if entry["is_choice_option"]:
            choice_points.append({"level": entry["level"],
                                  "parent": entry["choice_parent"]})

    shared = [a for a in actions if not a["is_choice_option"]]
    optional = [a for a in actions if a["is_choice_option"]]

    # Does each objective look like it matches something a student does?
    # A prompt to check, never a conclusion.
    objective_checks = []
    haystack = " ".join(
        (a["action"] + " " + " ".join(a["steps"])).lower() for a in actions)
    for objective in lesson["plan"].get("objectives") or []:
        words = {w for w in re.findall(r"[a-z]{5,}", objective.lower())}
        hits = sorted(w for w in words if w in haystack)
        verb = next((v for v in BLOOM if objective.lower().startswith(v)), None)
        objective_checks.append({
            "objective": objective,
            "cognitive_verb": verb,
            "words_also_in_student_actions": hits[:6],
            "verdict": "looks supported" if len(hits) >= 2 else "check this",
        })

    questions = []
    if is_alternate:
        questions.append(
            f"This lesson is in \"{group}\". It is a second version of a lesson "
            f"the unit teaches elsewhere, and a student does one or the other. "
            f"Do not credit both.")
    if not lesson.get("has_objectives") and lesson.get("has_lesson_plan"):
        questions.append(
            "No authored objective. There is nothing to anchor a forward "
            "alignment claim on.")
    if optional and not shared:
        questions.append(
            "Every student action here sits in a choice branch. Any claim is "
            "met by a fraction of the class.")
    if code_by_ai and code_by_student:
        questions.append(
            f"Code is written both ways here: {code_by_student} levels look "
            f"student-written, {code_by_ai} look AI-written at the student's "
            f"direction. The framework decides whether prompting counts.")
    if not actions and reading_levels:
        questions.append(
            "The student reads and watches but produces nothing. That may be "
            "correct for this lesson. It is not evidence of a performance.")

    return {
        "stable_id": lesson["stable_id"],
        "lesson_name": lesson["lesson_name"],
        "script_name": lesson["script_name"],
        "lesson_group_name": group or None,
        "is_alternate_progression": is_alternate,
        "content_hash": lesson["content_hash"],
        "has_lesson_plan": lesson.get("has_lesson_plan"),
        "objectives": objective_checks,
        "every_student": shared,
        "one_option_only": optional,
        "choice_points": choice_points,
        "produces": produces,
        "checked": checked,
        "authorship": {
            "code_levels_student_written": code_by_student,
            "code_levels_ai_written_at_student_direction": code_by_ai,
            "note": "Recorded, not judged. The policy is one written decision "
                    "per framework, not an implicit judgement per lesson.",
        },
        "reading_levels": reading_levels,
        "signals": signals,
        "open_questions": questions,
    }


def to_markdown(record):
    out = [f"# {record['lesson_name']} — what students do", ""]
    out.append(f"- `{record['stable_id']}`")
    if record["lesson_group_name"]:
        out.append(f"- Group: {record['lesson_group_name']}")
    if record["is_alternate_progression"]:
        out.append("- **Alternate progression. A student does this or the "
                   "main lesson, not both.**")
    out.append(f"- hash `{record['content_hash'][:12]}`")
    out.append("")

    if record["open_questions"]:
        out += ["## Questions this tool cannot answer", ""]
        out += [f"- {q}" for q in record["open_questions"]] + [""]

    out += ["## Stated objectives, against what students do", ""]
    if not record["objectives"]:
        out.append("*None authored.*")
        out.append("")
    for check in record["objectives"]:
        verb = f" _(verb: {check['cognitive_verb']})_" if check["cognitive_verb"] else ""
        out.append(f"- **{check['verdict']}**{verb} — {check['objective']}")
        if check["words_also_in_student_actions"]:
            out.append(f"  - shared wording: "
                       f"{', '.join(check['words_also_in_student_actions'])}")
    out.append("")

    out += ["## What every student does", ""]
    if not record["every_student"]:
        out.append("*Nothing outside a choice branch.*")
        out.append("")
    for step in record["every_student"]:
        out.append(f"- {step['action']} — `{step['level']}` "
                   f"({step['level_type']}, {step['word_count']} words)")
        for line in step["steps"][:4]:
            out.append(f"  - {line}")
    out.append("")

    if record["one_option_only"]:
        out += ["## What only some students do", "",
                "*Each student completes one option. A claim resting on these "
                "is met by a fraction of the class.*", ""]
        for step in record["one_option_only"]:
            out.append(f"- {step['action']} — `{step['level']}` "
                       f"(option of `{step['choice_parent']}`)")
        out.append("")

    if record["produces"]:
        out += ["## What students produce", ""]
        out += [f"- {p['artifact']} — `{p['level']}`" for p in record["produces"]]
        out.append("")

    if record["checked"]:
        out += ["## What is checked", ""]
        out += [f"- `{c['level']}` — {c['how']}" for c in record["checked"]]
        out.append("")

    authorship = record["authorship"]
    if authorship["code_levels_student_written"] or \
            authorship["code_levels_ai_written_at_student_direction"]:
        out += ["## Who writes the code", "",
                f"- student written: "
                f"{authorship['code_levels_student_written']} levels",
                f"- AI written at the student's direction: "
                f"{authorship['code_levels_ai_written_at_student_direction']} levels",
                "", f"*{authorship['note']}*", ""]

    signals = record["signals"]
    out += ["## Where these actions came from", "",
            f"- level type: {signals['level_type']} levels",
            f"- a \"Do This\" heading: {signals['do_this']}",
            f"- a \"Directions:\" heading: {signals['directions']}",
            f"- numbered steps: {signals['numbered']}",
            f"- an imperative heading: {signals['imperative']}",
            "",
            "*The level type is the primary signal. It is authored metadata, "
            "so it survives a change of house writing style; a heading does "
            "not.*", ""]
    return "\n".join(out)
