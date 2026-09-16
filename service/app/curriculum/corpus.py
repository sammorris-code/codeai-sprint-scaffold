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
import time

from .lessons import StandardsCatalog, extract_unit
from .levels import LevelIndex
from .repo import SUBDIRS, Repo


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
    name = course_key
    try:
        offering = json.loads(repo.read_text(
            f"{SUBDIRS['course_offerings']}/{doc.get('properties', {}).get('family_name', '')}.json"))
        name = offering.get("display_name") or name
    except Exception:
        pass
    return {"course_key": course_key, "course_name": name, "units": units}


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
    "stable_id", "script_name", "unit_name", "lesson_key", "lesson_name",
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

    courses_by_unit = {}
    for course in result["courses"]:
        for unit in course["units"]:
            courses_by_unit.setdefault(unit["script_name"], []).append(
                course["course_key"])

    rows = []
    for script_name, unit in result["units"].items():
        (out / "lessons" / script_name).mkdir(parents=True, exist_ok=True)
        (out / "levels" / script_name).mkdir(parents=True, exist_ok=True)
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

            level_dir = out / "levels" / script_name
            (level_dir / f"{stem}.levels.json").write_text(
                json.dumps({"stable_id": lesson["stable_id"],
                            "levels": lesson["levels"]},
                           indent=2, ensure_ascii=False), encoding="utf-8")
            (level_dir / f"{stem}.levels.md").write_text(
                _levels_markdown(lesson), encoding="utf-8")

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
             "serialized_at": u["serialized_at"],
             "published_state": u["published_state"],
             "lesson_count": len(u["lessons"]),
             "courses": courses_by_unit.get(s, [])}
            for s, u in result["units"].items()
        ],
        "totals": totals(result),
        "lessons": rows,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "warnings.json").write_text(
        json.dumps(result["warnings"], indent=2, ensure_ascii=False),
        encoding="utf-8")

    log(f"  wrote {len(rows)} lessons to {out}")
    return manifest


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
