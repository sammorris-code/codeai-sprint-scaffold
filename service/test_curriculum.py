#!/usr/bin/env python3
"""Tests curriculum extraction against a synthetic upstream repository.

    python3 service/test_curriculum.py

Every trap this pipeline can fall into produces a corpus that looks fine. The
extraction completes, reports no error, and the number is wrong. So the fixture
repository below is built to contain one of each, and the tests assert on the
thing that would otherwise be silent:

  - a level whose file name cannot exist on Windows, written into the tree with
    `git update-index` so it is in the commit but not on any disk
  - a DSL level whose file name is sanitised and does not match its own `name`
  - a `bubble_choice` parent holding no text, with the words in its children
  - a `Panels` level with its text in a list rather than a string
  - a `.multi` level authored with curly quotes
  - a unit whose displayed numbers disagree with its positions
  - a lesson with no lesson plan, and one with no authored objective
  - a lesson key that is a former title
  - two standards files with different column layouts

No network and no database. The repository is built here, committed here, and
thrown away afterwards.

What this does NOT cover is `load_curriculum.py`, which needs Postgres. See
the note at the bottom.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from service.app.curriculum import corpus                     # noqa: E402
from service.app.curriculum.repo import Repo                  # noqa: E402

failures, passes = [], 0


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"  ok    {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------------------
# The fixture repository
# ---------------------------------------------------------------------------

UNIT = "demo-unit-2026"

COURSE = {
    "name": "demo-course-2026",
    "script_names": [UNIT, "demo-capstone-2026"],
    # The trap: blank, then numbered. Position 2 and displayed number 2 are
    # different units.
    "unit_prefixes": ["", "1"],
    "properties": {"family_name": "demo-course", "version_year": "2026"},
}

CAPSTONE_COURSE_UNIT = "demo-capstone-2026"


def script_json(script_name, lessons, activities, sections, script_levels,
                objectives, standards_rows):
    return {
        "script": {"name": script_name, "serialized_at": "2026-09-01 00:00:00 UTC",
                   "published_state": "stable",
                   "properties": {"title": "Demo Unit"}},
        "lessons": lessons,
        "lesson_activities": activities,
        "activity_sections": sections,
        "script_levels": script_levels,
        "levels_script_levels": [],
        "objectives": objectives,
        "lessons_standards": standards_rows,
        "lessons_opportunity_standards": [],
        "resources": [{"name": "Unit Guide", "url": "https://example.org/guide",
                       "key": "guide",
                       "properties": {"audience": "Verified Teacher",
                                      "type": "Answer Key"}}],
        "lessons_resources": [
            {"seeding_key": {"lesson.key": "Lesson 1: Old Title",
                             "resource.key": "guide"}}],
        "vocabularies": [], "lessons_vocabularies": [], "learning_goals": [],
    }


def build_fixture(root):
    cfg = root / "dashboard" / "config"
    for sub in ("courses", "course_offerings", "scripts_json", "standards",
                "levels/custom/panels", "levels/custom/weblab2", "scripts"):
        (cfg / sub).mkdir(parents=True, exist_ok=True)

    (cfg / "courses" / "demo-course-2026.course").write_text(
        json.dumps(COURSE), encoding="utf-8")
    (cfg / "course_offerings" / "demo-course.json").write_text(
        json.dumps({"display_name": "Demo Course"}), encoding="utf-8")

    # --- two standards files, deliberately different layouts --------------
    (cfg / "standards" / "csta2026_standards.csv").write_text(
        "framework,category,standard,description\n"
        "csta2026,ALG,HS-ALG-IM-10,\"Implement an algorithm, using iteration.\"\n",
        encoding="utf-8")
    (cfg / "standards" / "ai4k12-2021_standards.csv").write_text(
        "framework,parent,name,category,description,type\n"
        "ai4k12-2021,BI-3,Learning,3-A-i,Computers can learn from data,Concept\n",
        encoding="utf-8")

    # --- levels in the XML directory --------------------------------------
    def level_file(path, root_tag, config):
        (cfg / path).write_text(
            f"<{root_tag}>\n  <config><![CDATA[{json.dumps(config)}]]></config>\n"
            f"</{root_tag}>\n", encoding="utf-8")

    level_file("levels/custom/panels/demo-panels-1.level", "Panels",
               {"properties": {"panels": [
                   {"text": "Random Access Memory is volatile storage."},
                   {"text": "A hard disk keeps its contents without power."}]}})
    level_file("levels/custom/weblab2/demo-template-1.level", "Weblab2",
               {"properties": {"start_sources": {"files": {}}, "submittable": True}})

    # --- DSL levels, file names sanitised ---------------------------------
    # The file is demo_choice_1.bubble_choice; the level is demo-choice-1.
    (cfg / "scripts" / "demo_choice_1.bubble_choice").write_text(
        "name 'demo-choice-1'\n"
        "display_name 'Pick a scenario'\n"
        "description 'Choose one scenario and build it.'\n"
        "\nsublevels\n"
        "level 'demo-choice-1a'\n"
        "level 'demo-choice-1b'\n", encoding="utf-8")
    (cfg / "scripts" / "demo_choice_1a.external").write_text(
        "name 'demo-choice-1a'\n"
        "markdown <<MARKDOWN\n"
        "Build the ticket booking scenario end to end and test every branch.\n"
        "MARKDOWN\n", encoding="utf-8")
    (cfg / "scripts" / "demo_choice_1b.external").write_text(
        "name 'demo-choice-1b'\n"
        "markdown <<MARKDOWN\n"
        "Build the library lending scenario end to end and test every branch.\n"
        "MARKDOWN\n", encoding="utf-8")

    # Curly quotes. A parser that knows only ' and " reads this as empty.
    (cfg / "scripts" / "demo_curly_1.multi").write_text(
        "name 'demo-curly-1'\n\n"
        "question ‘Which of these is a volatile form of memory?’\n\n"
        "right ‘RAM’\n"
        "wrong ‘Hard disk’\n"
        "wrong ‘Solid state drive’\n", encoding="utf-8")

    # --- the unit file ----------------------------------------------------
    lessons = [
        # has_lesson_plan false, and it holds a position
        {"key": "Pre-Assessment", "name": "Pre-Assessment",
         "relative_position": 1, "absolute_position": 1,
         "has_lesson_plan": False, "properties": {"assessment": True}},
        # the key is a former title; the name has moved on
        {"key": "Lesson 1: Old Title", "name": "Lesson 1: New Title",
         "relative_position": 1, "absolute_position": 2,
         "has_lesson_plan": True,
         "properties": {"overview": "Overview text.",
                        "student_overview": "Student overview text."}},
        # a lesson with a plan but no authored objective
        {"key": "Lesson 2: Project", "name": "Lesson 2: Project",
         "relative_position": 2, "absolute_position": 3,
         "has_lesson_plan": True, "properties": {"overview": "Project."}},
    ]
    activities = [
        {"key": "act-1", "position": 1,
         "seeding_key": {"lesson.key": "Lesson 1: Old Title"}},
        {"key": "act-2", "position": 1,
         "seeding_key": {"lesson.key": "Lesson 2: Project"}},
        {"key": "act-0", "position": 1,
         "seeding_key": {"lesson.key": "Pre-Assessment"}},
    ]
    sections = [
        {"key": "sec-1", "position": 1,
         "properties": {"name": "Explore", "duration": 30,
                        "description": "Teacher notes.",
                        "tips": [{"type": "teachingTip", "markdown": "A tip."}]},
         "seeding_key": {"activity_section.key": "sec-1",
                         "lesson_activity.key": "act-1"}},
        {"key": "sec-2", "position": 1,
         "properties": {"name": "Build", "duration": 45},
         "seeding_key": {"activity_section.key": "sec-2",
                         "lesson_activity.key": "act-2"}},
        {"key": "sec-0", "position": 1, "properties": {},
         "seeding_key": {"activity_section.key": "sec-0",
                         "lesson_activity.key": "act-0"}},
    ]
    script_levels = [
        {"position": 1, "activity_section_position": 1, "assessment": False,
         "bonus": False, "level_keys": ["demo-panels-1", "demo-curly-1"],
         "properties": {},
         "seeding_key": {"lesson.key": "Lesson 1: Old Title",
                         "activity_section.key": "sec-1"}},
        {"position": 1, "activity_section_position": 1, "assessment": False,
         "bonus": False, "level_keys": ["demo-choice-1", "demo-template-1"],
         "properties": {},
         "seeding_key": {"lesson.key": "Lesson 2: Project",
                         "activity_section.key": "sec-2"}},
        # This one points at a level whose file name has a colon in it.
        {"position": 1, "activity_section_position": 1, "assessment": True,
         "bonus": False, "level_keys": ["Deep Dive: Find the Changes"],
         "properties": {},
         "seeding_key": {"lesson.key": "Pre-Assessment",
                         "activity_section.key": "sec-0"}},
    ]
    objectives = [
        {"key": "obj-1",
         "properties": {"description": "Explain what volatile memory is."},
         "seeding_key": {"lesson.key": "Lesson 1: Old Title",
                         "objective.key": "obj-1"}},
    ]
    standards_rows = [
        {"seeding_key": {"lesson.key": "Lesson 1: Old Title",
                         "framework.shortcode": "csta2026",
                         "standard.shortcode": "HS-ALG-IM-10"}},
        {"seeding_key": {"lesson.key": "Lesson 1: Old Title",
                         "framework.shortcode": "ai4k12-2021",
                         "standard.shortcode": "3-A-i"}},
    ]
    (cfg / "scripts_json" / f"{UNIT}.script_json").write_text(
        json.dumps(script_json(UNIT, lessons, activities, sections,
                               script_levels, objectives, standards_rows)),
        encoding="utf-8")

    # A second unit, so the course has two and the numbering trap is visible.
    (cfg / "scripts_json" / f"{CAPSTONE_COURSE_UNIT}.script_json").write_text(
        json.dumps(script_json(
            CAPSTONE_COURSE_UNIT,
            [{"key": "Capstone Project", "name": "Capstone Project",
              "relative_position": 1, "absolute_position": 1,
              "has_lesson_plan": True, "properties": {"overview": "Ten days."}}],
            [], [], [], [], [])), encoding="utf-8")


def git(root, *args):
    done = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{done.stderr.decode('utf-8', 'replace')}")
    return done.stdout


def add_unwritable_level(root):
    """Put a level whose file name Windows forbids into the tree.

    `git update-index --cacheinfo` writes an entry straight into the index
    without going near the filesystem, which is the only way this path can
    exist on Windows — and it is exactly the shape of the 512 real paths that
    break a working-tree checkout.
    """
    content = ("<External>\n  <config><![CDATA["
               + json.dumps({"properties": {
                   "markdown": "Find the changes the model made to this code."}})
               + "]]></config>\n</External>\n")
    proc = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=root,
                          input=content.encode("utf-8"), capture_output=True)
    sha = proc.stdout.decode().strip()
    # protectNTFS makes git refuse to record a path Windows cannot represent,
    # which is normally the right call and here is the thing being tested.
    # Upstream carries 512 of these; they were committed on other platforms.
    git(root, "-c", "core.protectNTFS=false", "update-index", "--add",
        "--cacheinfo",
        f"100644,{sha},dashboard/config/levels/custom/weblab2/"
        f"Deep Dive: Find the Changes.level")
    return sha


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="corpus-test-"))
    repo_dir = tmp / "cdo"
    out_dir = tmp / "out"
    repo_dir.mkdir(parents=True)
    try:
        git(repo_dir, "init", "-q")
        git(repo_dir, "config", "user.email", "test@example.org")
        git(repo_dir, "config", "user.name", "Test")
        build_fixture(repo_dir)
        git(repo_dir, "add", "-A")
        sha = add_unwritable_level(repo_dir)
        git(repo_dir, "commit", "-q", "-m", "fixture")

        print("\nExtracting the fixture repository")
        with Repo(str(repo_dir)) as repo:
            result = corpus.extract(repo, ["demo-course-2026"],
                                    cache_dir=None, log=lambda *a: None)
            manifest = corpus.write(result, str(out_dir), log=lambda *a: None)

        lessons = {l["stable_id"]: l
                   for u in result["units"].values() for l in u["lessons"]}
        by_name = {}
        for lesson in lessons.values():
            for lv in lesson["levels"]:
                by_name[lv["level_name"]] = lv

        print("\nThe file that cannot exist on disk")
        on_disk = (repo_dir / "dashboard" / "config" / "levels" / "custom"
                   / "weblab2")
        check("the colon path is not on disk",
              not any(":" in p.name for p in on_disk.iterdir()),
              "the fixture wrote it to disk, so it is not testing anything")
        check("it is in the git tree", bool(sha))
        check("the extractor read it",
              "Deep Dive: Find the Changes" in by_name,
              f"found: {sorted(by_name)}")
        check("and got its words",
              by_name.get("Deep Dive: Find the Changes", {}).get("word_count", 0) > 0)

        print("\nSanitised DSL file names")
        check("demo-choice-1 resolved from a file named demo_choice_1",
              "demo-choice-1" in by_name)

        print("\nParent levels hold no text of their own")
        parent = by_name.get("demo-choice-1", {})
        kids = [by_name.get("demo-choice-1a"), by_name.get("demo-choice-1b")]
        check("both children were reached", all(kids))
        check("children carry the words",
              all(k and k["word_count"] > 0 for k in kids))
        check("children are marked as choice options",
              all(k and k["context"]["is_choice_option"] for k in kids))
        check("the parent is not",
              parent.get("context", {}).get("is_choice_option") is False)
        check("the choice parent is named on the child",
              kids[0]["context"]["choice_parent"] == "demo-choice-1")

        print("\nText held in a list, not a string")
        panels = by_name.get("demo-panels-1", {})
        check("Panels text was read", panels.get("word_count", 0) >= 10,
              f"word_count={panels.get('word_count')}")
        check("both panels were read", "hard disk" in
              panels.get("student_text", "").lower())

        print("\nCurly quotes in a DSL level")
        curly = by_name.get("demo-curly-1", {})
        check("the question was read", "volatile" in
              curly.get("student_text", "").lower(),
              f"student_text={curly.get('student_text')!r}")
        check("all three options were read",
              len(curly.get("answer_options", [])) == 3,
              f"{curly.get('answer_options')}")
        check("the right answer is marked",
              [o["text"] for o in curly.get("answer_options", [])
               if o["correct"]] == ["RAM"])

        print("\nA level that genuinely has no words")
        template = by_name.get("demo-template-1", {})
        check("template has no student text",
              template.get("word_count") == 0)
        check("but is flagged as having starter code",
              template.get("has_starter_code") is True)

        print("\nUnit numbering")
        units = manifest["courses"][0]["units"]
        check("position 1 has a blank displayed number",
              units[0]["displayed_number"] == "",
              f"{units[0]}")
        check("position 2 is displayed as 1",
              units[1]["displayed_number"] == "1", f"{units[1]}")
        check("position and displayed number are not the same field",
              units[1]["position"] == 2 and units[1]["displayed_number"] == "1")

        print("\nLesson identity")
        lesson = lessons[f"{UNIT}::Lesson 1: Old Title"]
        check("stable_id is script_name::lesson_key",
              lesson["stable_id"] == f"{UNIT}::Lesson 1: Old Title")
        check("lesson_name is the current title",
              lesson["lesson_name"] == "Lesson 1: New Title")
        check("lesson_token comes from the name, not the key",
              lesson["lesson_token"] == "1", lesson["lesson_token"])
        pre = lessons[f"{UNIT}::Pre-Assessment"]
        check("a lesson with no plan is kept",
              pre["has_lesson_plan"] is False)
        check("it still holds a position",
              pre["absolute_position"] == 1)
        check("a lesson with no objective is flagged",
              lessons[f"{UNIT}::Lesson 2: Project"]["has_objectives"] is False)
        check("and warned about",
              any(w["kind"] == "no_authored_objective"
                  for w in result["warnings"]))
        check("a lesson with an objective is not flagged",
              lesson["has_objectives"] is True)

        print("\nStandards citations, two different column layouts")
        cited = {s["shortcode"]: s for s in lesson["plan"]["standards"]}
        check("csta2026 resolved (code in the `standard` column)",
              cited.get("HS-ALG-IM-10", {}).get("resolved") is True)
        check("its statement is the source text",
              "iteration" in (cited.get("HS-ALG-IM-10", {})
                              .get("statement") or ""))
        check("ai4k12 resolved (code in the `category` column)",
              cited.get("3-A-i", {}).get("resolved") is True)

        print("\nAnswer keys are flagged, not collected")
        res = lesson["plan"]["resources"]
        check("the restricted resource is flagged",
              any(r["is_answer_key"] for r in res), f"{res}")
        check("only the link is kept",
              all(set(r) == {"name", "url", "audience", "is_answer_key"}
                  for r in res))

        print("\nChange detection")
        first = lesson["content_hash"]
        with Repo(str(repo_dir)) as repo:
            again = corpus.extract(repo, ["demo-course-2026"], cache_dir=None,
                                   log=lambda *a: None)
        same = {l["stable_id"]: l for u in again["units"].values()
                for l in u["lessons"]}[lesson["stable_id"]]["content_hash"]
        check("the same content hashes the same", first == same)

        # Change one word of student text and confirm the hash moves.
        path = (repo_dir / "dashboard" / "config" / "scripts"
                / "demo_curly_1.multi")
        path.write_text(path.read_text(encoding="utf-8")
                        .replace("volatile", "temporary"), encoding="utf-8")
        git(repo_dir, "add", "-A")
        git(repo_dir, "commit", "-q", "-m", "edit a level")
        with Repo(str(repo_dir)) as repo:
            edited = corpus.extract(repo, ["demo-course-2026"], cache_dir=None,
                                    log=lambda *a: None)
        moved = {l["stable_id"]: l for u in edited["units"].values()
                 for l in u["lessons"]}
        check("editing student text moves the lesson hash",
              moved[lesson["stable_id"]]["content_hash"] != first)
        check("and leaves other lessons alone",
              moved[f"{UNIT}::Lesson 2: Project"]["content_hash"]
              == lessons[f"{UNIT}::Lesson 2: Project"]["content_hash"])

        print("\nThe corpus on disk")
        check("manifest.csv was written", (out_dir / "manifest.csv").exists())
        check("warnings.json was written", (out_dir / "warnings.json").exists())
        check("a lesson markdown was written",
              any((out_dir / "lessons" / UNIT).glob("*.md")))
        check("a levels markdown was written",
              any((out_dir / "levels" / UNIT).glob("*.levels.md")))
        check("the manifest names the commit",
              len(manifest["provenance"]["source_commit"]) == 40)

        print("\nNothing was written upstream")
        status = git(repo_dir, "status", "--porcelain").decode().strip()
        check("the upstream clone is unchanged", status == "", status)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{passes} checks passed, {len(failures)} failed")
    if failures:
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nNot covered here: load_curriculum.py, which needs Postgres.\n"
          "Run it against a live database before trusting the stale pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
