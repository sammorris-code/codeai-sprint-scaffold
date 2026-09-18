"""Walking courses to units to lessons, and writing the corpus out.

The corpus is the evidence base for alignment. It replaces reading lesson-plan
PDFs and recording matches in a spreadsheet, which failed three ways: PDFs are
rendered output that has lost the structure, a spreadsheet cannot tell you when
the curriculum changed, and neither can be rebuilt cheaply for the next state.

Two structural facts drive the shape of what comes out.

**Units are shared between courses.** A full-year course reuses the units of
both semesters. Each unit is therefore extracted exactly once and attributed to
every course that includes it, which is why the store has a `course_unit` join
table rather than a foreign key from unit to course. Counts overlap on purpose.

**A unit's displayed number is not its position.** AIF Semester 2 leaves the
first four units blank and numbers the last two 1 and 2, so "Semester 2, Unit 2"
means one thing by order and another by what is on the screen. Both are
recorded, separately, and neither is computed from the other. Sort by position,
display the number, and record `script_name` as the identifier.
"""
import csv
import io
import json
import os
import pathlib
import posixpath
import re
import time

from .distil import distil, to_markdown
from ..alignment_evidence.sources import extract as evidence_sources
from .lessons import StandardsCatalog, extract_unit
from .levels import LevelIndex
from .repo import SUBDIRS, Repo


YEAR_SUFFIX = re.compile(r"-(?:19|20)\d{2}$")

# Which courses are one semester of a longer course. A mapping CSV carries a
# semester column, and before this the value was typed on the command line by
# whoever ran the export — so a wrong label produced a wrong file and nothing
# caught it. This is a naming convention read from the course key, not a fact
# the curriculum states, so it is recorded for a person to confirm rather than
# trusted. Courses absent from this map have no semester, which is correct for
# almost all of them.
SEMESTER_BY_COURSE = {
    "ai-foundations-exploring-ai-and-cs-2026": "S1",
    "ai-foundations-designing-and-building-with-ai-2026": "S2",
}
# Words the plain title-caser gets wrong. Districts read these.
ACRONYMS = {"Ai": "AI", "Api": "API", "Apis": "APIs", "Cs": "CS",
            "Ui": "UI", "Ux": "UX", "Html": "HTML", "Css": "CSS",
            "Javascript": "JavaScript"}
# Kept lowercase unless they open the title.
SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on",
               "or", "the", "to", "with"}


class UnitNames:
    """Display names for units.

    A unit file carries no title of its own. The name a teacher sees comes
    from elsewhere — for units that are also standalone offerings, from
    `course_offerings/<key>.json`; for the rest it lives in translation files
    this extraction does not read.

    So the name is looked up where it exists and derived from the slug where
    it does not, and which of the two happened is recorded. A derived name is
    a readable label, not an authored title, and `unit_name_source` is there
    so nothing downstream has to guess which it is holding. The identifier is
    always `script_name`; this field is only ever for display.
    """

    def __init__(self, repo):
        self.by_key = {}
        for path in repo.list("course_offerings", suffixes=(".json",)):
            try:
                doc = json.loads(repo.read_text(path))
            except ValueError:
                continue
            key = doc.get("key") or posixpath.basename(path)[:-len(".json")]
            if doc.get("display_name"):
                self.by_key[key] = doc["display_name"]

    @staticmethod
    def humanise(script_name):
        words = YEAR_SUFFIX.sub("", script_name).replace("-", " ").split()
        out = []
        for i, word in enumerate(words):
            capped = word.capitalize()
            if word.lower() in SMALL_WORDS and i > 0:
                out.append(word.lower())
            else:
                out.append(ACRONYMS.get(capped, capped))
        return " ".join(out)

    def resolve(self, script_name):
        for candidate in (script_name, YEAR_SUFFIX.sub("", script_name)):
            if candidate in self.by_key:
                return self.by_key[candidate], "offering"
        return self.humanise(script_name), "derived"


def load_course(repo, course_key):
    """One course file: which units, in what order, numbered how."""
    doc = json.loads(repo.read_text(f"{SUBDIRS['courses']}/{course_key}.course"))
    scripts = doc.get("script_names") or []
    prefixes = doc.get("unit_prefixes") or []
    units = []
    for i, script in enumerate(scripts):
        units.append({
            "script_name": script,
            "position": i + 1,
            # Blank is a real value here, not a missing one. Keep it as given.
            "displayed_number": prefixes[i] if i < len(prefixes) else None,
        })
    family = (doc.get("properties") or {}).get("family_name") or ""
    name = course_key
    try:
        offering = json.loads(repo.read_text(
            f"{SUBDIRS['course_offerings']}/{family}.json"))
        name = offering.get("display_name") or name
    except Exception:                                      # noqa: BLE001
        name = UnitNames.humanise(course_key)
    return {"course_key": course_key, "course_name": name,
            "semester": SEMESTER_BY_COURSE.get(course_key), "units": units}


class IndexCache:
    """The level-name index, kept between runs.

    Building it means opening every one of ~36,000 DSL files to read the
    `name` line inside, which takes a few minutes. The answer only changes
    when the commit changes, so it is cached under the commit id. Deleting the
    cache directory is always safe.
    """

    def __init__(self, directory, commit):
        self.path = long_path(directory) / f"level-index-{commit[:12]}.json"

    def load(self):
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    def save(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload), encoding="utf-8")


def build_index(repo, cache_dir=None, log=print):
    index = LevelIndex(repo)
    cache = IndexCache(cache_dir, repo.commit) if cache_dir else None
    cached = cache.load() if cache else None
    if cached:
        index.by_name = cached["by_name"]
        index.stats = cached["stats"]
        log(f"  level index: {len(index.by_name):,} names (cached)")
        return index

    started = time.time()
    log("  level index: reading both level directories (a few minutes)...")
    stats = index.build()
    log(f"  level index: {stats['total_names']:,} names "
        f"({stats['names_from_xml']:,} from levels/, "
        f"{stats['names_from_dsl']:,} from scripts/) "
        f"in {time.time() - started:.0f}s")
    if cache:
        cache.save({"by_name": index.by_name, "stats": index.stats})
    return index


def extract(repo, course_keys, cache_dir=None, log=print):
    """Extract every unit in the named courses. Units shared between courses
    are read once and attributed to each."""
    index = build_index(repo, cache_dir, log)
    catalog = StandardsCatalog(repo)
    unit_names = UnitNames(repo)
    log(f"  standards: {len(catalog.by_framework)} frameworks available "
        f"for resolving the curriculum's own citations")

    courses = [load_course(repo, key) for key in course_keys]

    wanted = []
    for course in courses:
        for unit in course["units"]:
            if unit["script_name"] not in wanted:
                wanted.append(unit["script_name"])
    log(f"  units: {len(wanted)} distinct across {len(courses)} courses")

    units = {}
    warnings = []
    for script_name in wanted:
        try:
            result = extract_unit(repo, script_name, index, catalog)
        except Exception as exc:                       # noqa: BLE001
            warnings.append({"kind": "unit_failed", "script_name": script_name,
                             "detail": f"{type(exc).__name__}: {exc}"})
            log(f"    {script_name}: FAILED ({type(exc).__name__}: {exc})")
            continue
        # The unit file has no title in it, so the display name is resolved
        # here and stamped on the lessons that will carry it downstream.
        display_name, source = unit_names.resolve(script_name)
        result["unit_name"] = display_name
        result["unit_name_source"] = source
        for lesson in result["lessons"]:
            lesson["unit_name"] = display_name

        units[script_name] = result
        warnings.extend(result["warnings"])
        words = sum(lv["word_count"] for l in result["lessons"] for lv in l["levels"])
        log(f"    {script_name}: {len(result['lessons'])} lessons, "
            f"{sum(len(l['levels']) for l in result['lessons'])} levels, "
            f"{words:,} student words")

    return {"commit": repo.commit, "courses": courses, "units": units,
            "warnings": warnings, "index_stats": index.stats}


# ---------------------------------------------------------------------------
# Writing the corpus out
# ---------------------------------------------------------------------------

MANIFEST_COLUMNS = [
    "stable_id", "script_name", "unit_name", "lesson_group_name", "lesson_key",
    "lesson_name",
    "lesson_token", "relative_position", "absolute_position",
    "has_lesson_plan", "has_objectives", "objective_count", "standard_count",
    "level_count", "choice_level_count", "student_word_count",
    "duration_minutes", "content_hash", "courses",
]


def _lesson_row(lesson, courses_for_unit):
    return {
        "stable_id": lesson["stable_id"],
        "script_name": lesson["script_name"],
        "unit_name": lesson["unit_name"],
        "lesson_group_name": lesson["lesson_group_name"],
        "lesson_key": lesson["lesson_key"],
        "lesson_name": lesson["lesson_name"],
        "lesson_token": lesson["lesson_token"],
        "relative_position": lesson["relative_position"],
        "absolute_position": lesson["absolute_position"],
        "has_lesson_plan": lesson["has_lesson_plan"],
        "has_objectives": lesson["has_objectives"],
        "objective_count": len(lesson["plan"]["objectives"]),
        "standard_count": len(lesson["plan"]["standards"]),
        "level_count": len(lesson["levels"]),
        "choice_level_count": sum(1 for lv in lesson["levels"]
                                  if lv["context"]["is_choice_option"]),
        "student_word_count": sum(lv["word_count"] for lv in lesson["levels"]),
        "duration_minutes": lesson["plan"]["duration_minutes"],
        "content_hash": lesson["content_hash"],
        "courses": "|".join(courses_for_unit),
    }


def _lesson_markdown(lesson):
    out = [f"# {lesson['lesson_name']}", ""]
    out.append(f"- Unit: `{lesson['script_name']}` — {lesson['unit_name']}")
    if lesson.get("lesson_group_name"):
        out.append(f"- Group: {lesson['lesson_group_name']}")
    out.append(f"- Stable id: `{lesson['stable_id']}`")
    out.append(f"- Position: {lesson['relative_position']} in unit, "
               f"{lesson['absolute_position']} overall")
    if lesson["plan"]["duration_minutes"]:
        out.append(f"- Duration: {lesson['plan']['duration_minutes']} minutes")
    if not lesson["has_lesson_plan"]:
        out.append("- **No lesson plan.** Assessment shell or survey.")
    if not lesson["has_objectives"]:
        out.append("- **No authored objective.** Nothing to anchor a forward "
                   "alignment claim on.")
    out.append("")

    plan = lesson["plan"]
    if plan["objectives"]:
        out += ["## Objectives", ""] + [f"- {o}" for o in plan["objectives"]] + [""]
    if plan["standards"]:
        out += ["## Standards the authors cite", "",
                "*Their claims, not evidence. A useful prior and a cross-check.*", ""]
        for s in plan["standards"]:
            text = s["statement"] or "*(not resolved)*"
            out.append(f"- `{s['framework']}` **{s['shortcode']}** — {text}")
        out.append("")
    for label, key in (("Overview", "overview_md"),
                       ("Student overview", "student_overview_md"),
                       ("Purpose", "purpose_md"),
                       ("Preparation", "preparation_md"),
                       ("Assessment opportunities", "assessment_opportunities_md")):
        if plan.get(key):
            out += [f"## {label}", "", plan[key], ""]

    if plan["activities"]:
        out += ["## Teaching guide", ""]
        for act in plan["activities"]:
            for sec in act["sections"]:
                title = sec["name"] or sec["progression_name"] or "Section"
                mins = f" ({sec['duration_minutes']} min)" if sec["duration_minutes"] else ""
                out += [f"### {title}{mins}", ""]
                if sec["description_md"]:
                    out += [sec["description_md"], ""]
                for tip in sec["tips"]:
                    if isinstance(tip, dict) and tip.get("markdown"):
                        out += [f"> **{tip.get('type', 'tip')}:** {tip['markdown']}", ""]
    if plan["resources"]:
        out += ["## Resources", ""]
        for r in plan["resources"]:
            flag = " **(answer key — restricted)**" if r["is_answer_key"] else ""
            out.append(f"- [{r['name']}]({r['url']}){flag}")
        out.append("")
    return "\n".join(out)


def _levels_markdown(lesson):
    out = [f"# {lesson['lesson_name']} — student instructions", "",
           f"- Stable id: `{lesson['stable_id']}`",
           f"- {len(lesson['levels'])} levels, in the order a student meets them",
           f"- {sum(lv['word_count'] for lv in lesson['levels']):,} words", ""]
    for i, lv in enumerate(lesson["levels"], 1):
        ctx = lv["context"]
        head = f"## {i}. {lv['title'] or lv['level_name']}"
        out += [head, "",
                f"`{lv['level_name']}` · type `{lv['level_type']}` · "
                f"{lv['word_count']} words"]
        marks = []
        if ctx["is_choice_option"]:
            marks.append(f"**one option of a choice** (`{ctx['choice_parent']}`) — "
                         f"only some students do this")
        if ctx["is_assessment"]:
            marks.append("assessment")
        if ctx["is_bonus"]:
            marks.append("bonus")
        if marks:
            out.append("")
            out.append("> " + "; ".join(marks))
        out.append("")
        if lv["student_text"]:
            out += [lv["student_text"], ""]
        if lv["answer_options"]:
            out.append("Options:")
            for o in lv["answer_options"]:
                out.append(f"- {'**[correct]** ' if o['correct'] else ''}{o['text']}")
            out.append("")
    return "\n".join(out)


def long_path(path):
    """Windows refuses a path over 260 characters unless it is given in
    extended-length form.

    A corpus directory a few levels down, plus a unit slug, plus a lesson
    title, crosses that line for real AIF lessons — and the failure arrives as
    `FileNotFoundError` on a directory that certainly does exist, which reads
    like a bug anywhere except where it is. The `\\\\?\\` prefix lifts the cap.
    On every other platform this returns the path unchanged.
    """
    resolved = pathlib.Path(path).resolve()
    if os.name == "nt":
        text = str(resolved)
        if not text.startswith("\\\\?\\"):
            return pathlib.Path("\\\\?\\" + text)
    return resolved


def write(result, out_dir, log=print):
    """Write the corpus. One directory per unit, one pair of files per lesson."""
    out = long_path(out_dir)
    (out / "lessons").mkdir(parents=True, exist_ok=True)
    (out / "levels").mkdir(parents=True, exist_ok=True)
    # The distilled layer is written every time rather than behind a flag.
    # It is derived, so it goes stale the moment the corpus moves without it,
    # and a flag is a thing somebody forgets.
    (out / "distilled").mkdir(parents=True, exist_ok=True)
    (out / "evidence").mkdir(parents=True, exist_ok=True)

    courses_by_unit = {}
    for course in result["courses"]:
        for unit in course["units"]:
            courses_by_unit.setdefault(unit["script_name"], []).append(
                course["course_key"])

    rows = []
    distilled = []
    for script_name, unit in result["units"].items():
        (out / "lessons" / script_name).mkdir(parents=True, exist_ok=True)
        (out / "levels" / script_name).mkdir(parents=True, exist_ok=True)
        (out / "distilled" / script_name).mkdir(parents=True, exist_ok=True)
        (out / "evidence" / script_name).mkdir(parents=True, exist_ok=True)
        for lesson in unit["lessons"]:
            stem = f"{lesson['absolute_position']:02d}-{lesson['slug']}"
            # Names are built by concatenation, not with_suffix(). A stem like
            # `05-capstone.levels` has `.levels` read as its extension, so
            # with_suffix('.md') replaces it instead of adding to it and the
            # file quietly lands at `05-capstone.md`.
            plan_dir = out / "lessons" / script_name
            (plan_dir / f"{stem}.json").write_text(
                json.dumps(lesson, indent=2, ensure_ascii=False), encoding="utf-8")
            (plan_dir / f"{stem}.md").write_text(
                _lesson_markdown(lesson), encoding="utf-8")
            (out / "evidence" / script_name / f"{stem}.sources.json").write_text(
                json.dumps(evidence_sources(lesson), indent=2, ensure_ascii=False), encoding="utf-8")

            level_dir = out / "levels" / script_name
            (level_dir / f"{stem}.levels.json").write_text(
                json.dumps({"stable_id": lesson["stable_id"],
                            "levels": lesson["levels"]},
                           indent=2, ensure_ascii=False), encoding="utf-8")
            (level_dir / f"{stem}.levels.md").write_text(
                _levels_markdown(lesson), encoding="utf-8")

            record = distil(lesson)
            distilled.append(record)
            distil_dir = out / "distilled" / script_name
            (distil_dir / f"{stem}.actions.json").write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            (distil_dir / f"{stem}.actions.md").write_text(
                to_markdown(record), encoding="utf-8")

            rows.append(_lesson_row(lesson, courses_by_unit.get(script_name, [])))

    rows.sort(key=lambda r: (r["script_name"], r["absolute_position"]))

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=MANIFEST_COLUMNS,
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    (out / "manifest.csv").write_text(buf.getvalue(), encoding="utf-8")

    manifest = {
        "provenance": {
            "source_repo": "code-dot-org/code-dot-org",
            "source_branch": "staging",
            "source_commit": result["commit"],
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "extractor": "service/extract_curriculum.py",
        },
        "index_stats": result["index_stats"],
        "courses": [
            {"course_key": c["course_key"], "course_name": c["course_name"],
             "units": c["units"]} for c in result["courses"]
        ],
        "units": [
            {"script_name": s, "unit_name": u["unit_name"],
             "unit_name_source": u.get("unit_name_source", "derived"),
             "serialized_at": u["serialized_at"],
             "published_state": u["published_state"],
             "lesson_count": len(u["lessons"]),
             "courses": courses_by_unit.get(s, [])}
            for s, u in result["units"].items()
        ],
        "totals": totals(result),
        "distilled": distil_summary(distilled),
        "instructional_inventory": {"source_directory": "evidence", "status": "awaiting_synthesis",
                                   "synthesize_with": "service/standards_pipeline.py --corpus PATH --stage inventory --live"},
        "lessons": rows,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "warnings.json").write_text(
        json.dumps(result["warnings"], indent=2, ensure_ascii=False),
        encoding="utf-8")

    log(f"  wrote {len(rows)} lessons to {out}")
    return manifest


def distil_summary(records):
    """How well the distilled layer reached the corpus.

    Reported every run rather than assumed. If the share of lessons with no
    student action ever climbs, the signal has stopped working and the layer
    is quietly worth less than it looks.
    """
    taught = [r for r in records if r["has_lesson_plan"]]
    with_action = [r for r in taught if r["every_student"] or r["one_option_only"]]
    from_prose = [r for r in taught
                  if r["signals"]["do_this"] or r["signals"]["directions"]]
    return {
        "lessons": len(records),
        "taught_lessons": len(taught),
        "with_a_student_action": len(with_action),
        "reached_by_a_prose_marker_alone": len(from_prose),
        "alternate_progressions": sum(
            1 for r in records if r["is_alternate_progression"]),
        "lessons_with_open_questions": sum(
            1 for r in records if r["open_questions"]),
        "code_student_authored": sum(
            r["authorship"]["student_authored"] for r in records),
        "code_student_specified": sum(
            r["authorship"]["student_specified"] for r in records),
        "code_outcome_prompted": sum(
            r["authorship"]["outcome_prompted"] for r in records),
        "code_counts_as_writing": sum(
            r["authorship"]["counts_as_writing_under_policy"] for r in records),
        "code_borderline": sum(
            len(r["authorship"]["borderline"]) for r in records),
    }


def totals(result):
    lessons = [l for u in result["units"].values() for l in u["lessons"]]
    levels = [lv for l in lessons for lv in l["levels"]]
    return {
        "courses": len(result["courses"]),
        "units": len(result["units"]),
        "lessons": len(lessons),
        "lessons_with_a_plan": sum(1 for l in lessons if l["has_lesson_plan"]),
        "lessons_with_student_content": sum(1 for l in lessons if l["levels"]),
        "lessons_without_an_objective": sum(
            1 for l in lessons if l["has_lesson_plan"] and not l["has_objectives"]),
        "levels": len(levels),
        "choice_levels": sum(1 for lv in levels if lv["context"]["is_choice_option"]),
        "levels_without_student_text": sum(1 for lv in levels if not lv["word_count"]),
        "student_words": sum(lv["word_count"] for lv in levels),
        "instructional_minutes": sum(
            l["plan"]["duration_minutes"] or 0 for l in lessons),
        "resource_links": sum(len(l["plan"]["resources"]) for l in lessons),
        "answer_key_links": sum(1 for l in lessons
                                for r in l["plan"]["resources"] if r["is_answer_key"]),
        "cited_standards": sum(len(l["plan"]["standards"]) for l in lessons),
        "cited_standards_unresolved": sum(
            1 for l in lessons for s in l["plan"]["standards"] if not s["resolved"]),
    }
