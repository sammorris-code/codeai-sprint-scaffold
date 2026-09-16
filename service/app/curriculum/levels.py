"""Student-facing level content: finding it, and reading all of it.

Lesson plans are what a teacher reads. Levels are the screens a student reads,
and they are stored somewhere else entirely, in two directories, in two
formats. This module is the part of the extraction that is easiest to get
wrong, so each trap is named where it is handled.

**Trap 1 — half the levels are not where you would look.**

    dashboard/config/levels/   XML wrapper, JSON config in a CDATA block.
                               The file name IS the level name.
    dashboard/config/scripts/  DSL text (.multi, .external, .bubble_choice,
                               .level_group, .match, ...). The file name is
                               SANITIZED and does not match the level name:
                               `ai_and_algorithmic_decisions_lesson10_..._2025`
                               on disk is
                               `ai-and-algorithmic-decisions-lesson10-...-2025`
                               to the curriculum. You must read the `name '...'`
                               line inside the file.

An index built from the first directory alone silently misses about a third of
all level references, and more than 40% in some AIF units. It reports no error.
That is why `build()` indexes both and counts what each contributed.

**Trap 2 — parent levels hold no text of their own.**

`bubble_choice` and `level_group` levels, and code levels carrying
`contained_level_names`, keep their content in their children. Reading only
parents finds roughly 40% of the student words and completes without
complaint. `expand()` is the fix: it walks a parent down to its children and
returns them in the order a student meets them.

**Trap 3 — a choice is not a sequence.** A `bubble_choice` offers options and
each student completes one. Children of one are marked `is_choice_option`, so
a later alignment claim can be capped rather than credited to the whole class.
"""
import html
import json
import posixpath
import re

# Extensions under scripts/ that define a level. Images and other assets share
# the directory, so this is a list rather than "everything that is not a .png".
DSL_SUFFIXES = (".multi", ".external", ".bubble_choice", ".level_group",
                ".match", ".text_match", ".evaluation_multi", ".contract_match",
                ".free_response", ".external_link", ".standalone_video")

# A quoted DSL value. Four delimiter pairs, not one: some authored files use
# curly quotes — `question ‘Which of these...’` — and a parser that knows only
# `'` and `"` reads those levels as empty. It finds the level, reports no
# error, and drops the question and every answer option. 30 AIF levels were
# lost to exactly this before the pairs were added.
_QUOTED = (r"(?:'(?P<sq>.*?)'"
           r'|"(?P<dq>.*?)"'
           r"|‘(?P<cs>.*?)’"
           r"|“(?P<cd>.*?)”)")


def _quoted_value(match):
    return next((g for g in (match.group("sq"), match.group("dq"),
                             match.group("cs"), match.group("cd"))
                 if g is not None), None)


# The DSL's own `name '...'` declaration. This, never the file name.
DSL_NAME = re.compile(r"^[ \t]*name[ \t]+" + _QUOTED, re.M | re.S)

# A child reference. Both `sublevels` (bubble_choice) and `page`
# (level_group) introduce these, and collecting them without caring which
# keyword opened the block is correct for both.
DSL_CHILD = re.compile(r"^[ \t]*level[ \t]+" + _QUOTED, re.M | re.S)

# key 'value', where the value may run over several lines.
DSL_FIELD = re.compile(r"^[ \t]*(\w+)[ \t]+" + _QUOTED, re.M | re.S)

# key <<TAG ... TAG
DSL_HEREDOC = re.compile(r"^[ \t]*(\w+)[ \t]+<<(\w+)\s*\n(.*?)\n[ \t]*\2[ \t]*$",
                         re.M | re.S)

XML_ROOT = re.compile(r"<\s*([A-Za-z_][\w.]*)")
XML_CONFIG = re.compile(r"<config>\s*<!\[CDATA\[(.*?)\]\]>\s*</config>", re.S)

# Level-config properties that hold words a student actually reads. Ordered so
# the longer, more instructional field comes first when several are present.
STUDENT_TEXT_FIELDS = ("long_instructions", "markdown", "short_instructions",
                       "text", "question", "content1", "instructions",
                       "display_name", "description")

# Properties whose value is a list of objects that each carry text, rather
# than a string. A `Panels` level — a multi-screen reading activity — keeps
# everything a student reads in `panels[].text`, so a reader that only looks
# at string properties finds the level, reports no error, and records it as
# having no content. That cost 37 AIF levels, several of them full pages of
# explanation.
STUDENT_TEXT_LIST_FIELDS = ("panels", "pages", "cards", "questions")
LIST_ITEM_TEXT_KEYS = ("text", "markdown", "content", "question")

# DSL fields holding student-visible prose, same idea.
DSL_TEXT_FIELDS = ("markdown", "description", "question", "content1", "text",
                   "title", "display_name", "banner")

TAGS = re.compile(r"<[^>]+>")


def strip_markup(text):
    """Drop HTML tags and unescape entities, for counting words only.

    The stored `student_text` keeps its original markup — it is evidence and
    must not be paraphrased or reshaped. This is used for `word_count`, where
    counting `<i class="fa fa-check">` as three words would inflate every
    total.
    """
    return html.unescape(TAGS.sub(" ", text or ""))


def word_count(text):
    return len(strip_markup(text).split())


class Level:
    """One level record, in the shape `lesson.levels` stores."""

    __slots__ = ("name", "level_type", "title", "student_text", "answer_options",
                 "children", "teacher_markdown", "submittable",
                 "ai_tutor_available", "has_starter_code", "has_validation",
                 "is_choice_parent", "source_path")

    def __init__(self, name, level_type, source_path):
        self.name = name
        self.level_type = level_type
        self.source_path = source_path
        self.title = None
        self.student_text = ""
        self.answer_options = []
        self.children = []
        self.teacher_markdown = None
        self.submittable = False
        self.ai_tutor_available = False
        self.has_starter_code = False
        self.has_validation = False
        self.is_choice_parent = False

    def as_record(self):
        return {
            "level_name": self.name,
            "level_type": self.level_type,
            "title": self.title,
            "student_text": self.student_text,
            "answer_options": self.answer_options,
            "teacher_markdown": self.teacher_markdown,
            "submittable": self.submittable,
            "ai_tutor_available": self.ai_tutor_available,
            "has_starter_code": self.has_starter_code,
            "has_validation": self.has_validation,
            "word_count": word_count(self.student_text),
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_dsl(name, text, path):
    """Read one DSL level file."""
    suffix = posixpath.splitext(path)[1].lstrip(".")
    lvl = Level(name, suffix, path)

    # Comment out a line with '#' and the DSL ignores it. So must we, or a
    # `#description '...'` left by an author becomes student text.
    live = "\n".join(l for l in text.splitlines()
                     if not l.lstrip().startswith("#"))

    # (key, value) in file order, so `right`/`wrong` keep their sequence.
    pairs = [(m.group(1), _quoted_value(m)) for m in DSL_FIELD.finditer(live)]
    fields = {}
    for key, value in pairs:
        if value is not None:
            fields.setdefault(key, value)
    for key, _tag, value in DSL_HEREDOC.findall(live):
        fields[key] = value

    lvl.title = fields.get("title") or fields.get("display_name")
    lvl.children = [v for m in DSL_CHILD.finditer(live)
                    if (v := _quoted_value(m)) is not None]
    lvl.is_choice_parent = suffix == "bubble_choice"
    lvl.submittable = str(fields.get("submittable", "")).lower() == "true"
    lvl.teacher_markdown = fields.get("teacher_markdown")

    # `right`/`wrong` are how .multi marks its options. Keeping which one is
    # correct matters: an alignment claim about assessment needs to know the
    # level checks an answer, not just that it asked something.
    for key, value in pairs:
        if key in ("right", "wrong") and value is not None:
            lvl.answer_options.append({"text": value,
                                       "correct": key == "right"})

    parts = [fields[k] for k in DSL_TEXT_FIELDS if fields.get(k)]
    lvl.student_text = "\n\n".join(parts)
    return lvl


def parse_xml(name, text, path):
    """Read one `.level` file: an XML wrapper around a JSON config."""
    root = XML_ROOT.search(text)
    lvl = Level(name, root.group(1) if root else "unknown", path)

    cfg_match = XML_CONFIG.search(text)
    if not cfg_match:
        return lvl
    try:
        cfg = json.loads(cfg_match.group(1))
    except ValueError:
        # A level whose config will not parse is reported by the caller rather
        # than dropped, so the count still reconciles.
        return lvl

    props = cfg.get("properties") or {}
    lvl.title = props.get("title") or props.get("display_name")
    lvl.teacher_markdown = props.get("teacher_markdown")
    lvl.submittable = bool(props.get("submittable"))
    lvl.ai_tutor_available = bool(props.get("ai_tutor_available"))
    lvl.has_starter_code = bool(props.get("start_sources")
                                or props.get("start_blocks")
                                or props.get("starter_code"))
    lvl.has_validation = bool(props.get("validation_code")
                              or props.get("validations"))

    # Three different ways a level points at children, all meaning the same
    # thing here: the text is not in this record.
    for key in ("contained_level_names", "sublevels", "project_template_level_name"):
        v = props.get(key) or cfg.get(key)
        if isinstance(v, list):
            lvl.children.extend(x for x in v if isinstance(x, str))
        elif isinstance(v, str):
            lvl.children.append(v)
    lvl.is_choice_parent = lvl.level_type.lower() in ("bubblechoice", "bubble_choice")

    for opt in (props.get("answers") or []):
        if isinstance(opt, dict):
            lvl.answer_options.append({"text": opt.get("text", ""),
                                       "correct": bool(opt.get("correct"))})

    parts = []
    for key in STUDENT_TEXT_FIELDS:
        v = props.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    for key in STUDENT_TEXT_LIST_FIELDS:
        v = props.get(key)
        if not isinstance(v, list):
            continue
        for item in v:
            if isinstance(item, str) and item.strip():
                parts.append(item)
            elif isinstance(item, dict):
                for text_key in LIST_ITEM_TEXT_KEYS:
                    got = item.get(text_key)
                    if isinstance(got, str) and got.strip():
                        parts.append(got)
                        break
    lvl.student_text = "\n\n".join(parts)
    return lvl


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------

class LevelIndex:
    """Level name -> where its content lives, across both directories."""

    def __init__(self, repo):
        self.repo = repo
        self.by_name = {}          # level name -> path
        self.stats = {}
        self.warnings = []
        self._cache = {}

    def build(self):
        """Index both directories. Counts are reported, never assumed."""
        xml_paths = self.repo.list("levels_xml", suffixes=(".level",))
        for p in xml_paths:
            self.by_name.setdefault(posixpath.basename(p)[:-len(".level")], p)
        from_xml = len(self.by_name)

        # The DSL half. Every candidate file must be opened, because the name
        # is inside it. This is the step an extractor is tempted to skip.
        dsl_paths = self.repo.list("levels_dsl", suffixes=DSL_SUFFIXES)
        unnamed = 0
        for path, text in self.repo.read_many(dsl_paths):
            m = DSL_NAME.search(text)
            if not m:
                unnamed += 1
                continue
            self.by_name.setdefault(m.group(2), path)

        self.stats = {
            "xml_files": len(xml_paths),
            "dsl_files": len(dsl_paths),
            "names_from_xml": from_xml,
            "names_from_dsl": len(self.by_name) - from_xml,
            "dsl_files_without_a_name_line": unnamed,
            "total_names": len(self.by_name),
        }
        if unnamed:
            self.warnings.append(
                f"{unnamed} files under scripts/ carry no `name` line and "
                f"could not be indexed.")
        return self.stats

    def get(self, name):
        """One parsed level, or None if the name resolves to nothing."""
        if name in self._cache:
            return self._cache[name]
        path = self.by_name.get(name)
        if path is None:
            self._cache[name] = None
            return None
        text = self.repo.read_text(path)
        lvl = (parse_xml(name, text, path) if path.endswith(".level")
               else parse_dsl(name, text, path))
        self._cache[name] = lvl
        return lvl

    def expand(self, name, _seen=None):
        """A level and every descendant, in the order a student meets them.

        This is trap 2. A parent contributes its own record — it often carries
        the framing text — and then its children follow. A parent with children
        keeps its own (usually short) text, so nothing is invented and nothing
        is lost.

        Returns a list of (level, context) pairs, where context marks a child
        of a choice parent so a claim on it can be capped at Introduced.
        """
        seen = _seen if _seen is not None else set()
        if name in seen:                  # cycles exist in authored data
            return []
        seen.add(name)

        lvl = self.get(name)
        if lvl is None:
            return [(None, {"missing_level_name": name})]

        out = [(lvl, {"is_choice_option": False, "choice_parent": None})]
        for child in lvl.children:
            for sub, ctx in self.expand(child, seen):
                if sub is None:
                    out.append((sub, ctx))
                    continue
                ctx = dict(ctx)
                if lvl.is_choice_parent:
                    ctx["is_choice_option"] = True
                    ctx["choice_parent"] = lvl.name
                out.append((sub, ctx))
        return out
