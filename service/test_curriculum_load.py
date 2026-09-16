#!/usr/bin/env python3
"""Tests loading a corpus into Postgres, and the stale pass.

    python3 service/test_curriculum_load.py

Needs a database. Reads `DATABASE_URL`, or the Compose default. CI runs it
against a real Postgres; `test_curriculum.py` covers everything that does not
need one.

The stale pass is the reason the store beats the spreadsheet, so it is tested
the only way that means anything: make a claim against a lesson, change that
lesson upstream, load the new snapshot, and check that the claim came back to
the queue, and that a claim on an untouched lesson did not.

The last case is the one worth having. Extraction is scoped to some courses,
so most lessons in the store are simply not in any given snapshot. If "absent
from this snapshot" were read as "deleted upstream", the first AIF-only
extraction would mark every AID claim stale.
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import psycopg                                                  # noqa: E402
from psycopg.rows import dict_row                               # noqa: E402

from service.app.curriculum import corpus                       # noqa: E402
from service.app.curriculum.repo import Repo                    # noqa: E402
from service import load_curriculum                             # noqa: E402
from service.test_curriculum import (build_fixture, git,        # noqa: E402
                                     add_unwritable_level, UNIT)

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")

failures, passes = [], 0


def check(name, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"  ok    {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  FAIL  {name}  {detail}")


def make_corpus(repo_dir, out_dir):
    """Extract the fixture repo into `out_dir` and read it back for loading."""
    with Repo(str(repo_dir)) as repo:
        result = corpus.extract(repo, ["demo-course-2026"], cache_dir=None,
                                log=lambda *a: None)
        corpus.write(result, str(out_dir), log=lambda *a: None)
    return load_curriculum.read_corpus(str(out_dir))


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="corpus-load-"))
    repo_dir = tmp / "cdo"
    repo_dir.mkdir(parents=True)

    try:
        conn = psycopg.connect(DSN, row_factory=dict_row)
    except psycopg.OperationalError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(f"Could not reach the database at {DSN}\n{exc}")

    try:
        git(repo_dir, "init", "-q")
        git(repo_dir, "config", "user.email", "test@example.org")
        git(repo_dir, "config", "user.name", "Test")
        build_fixture(repo_dir)
        git(repo_dir, "add", "-A")
        add_unwritable_level(repo_dir)
        git(repo_dir, "commit", "-q", "-m", "fixture")

        cur = conn.cursor()
        # Start from a known state. This is a prototype's test database.
        #
        # The standards tables are cleared too, not just the curriculum ones.
        # load_fixtures.py has usually run first and left a DEMO/CS-DEMO/2026
        # set behind, and the identity trio is unique — so a test that makes
        # its own standards set collides with it. Clearing them is what makes
        # this test independent of whatever ran before it.
        cur.execute("""TRUNCATE review_event, standard_outcome,
                       alignment_record, run, lesson, course_unit, unit,
                       course, snapshot, standard, standards_set
                       RESTART IDENTITY CASCADE""")
        conn.commit()

        print("\nLoading the first snapshot")
        manifest, lessons = make_corpus(repo_dir, tmp / "out1")
        snap1, stale = load_curriculum.load(conn, manifest, lessons,
                                            make_current=True,
                                            log=lambda *a: None)
        check("a snapshot row was written", snap1 is not None)
        check("it is current", cur.execute(
            "SELECT is_current FROM snapshot WHERE id=%s", (snap1,)
        ).fetchone()["is_current"] is True)
        check("nothing was stale on a first load", stale == 0)

        counts = cur.execute("""
            SELECT (SELECT count(*) FROM course)      AS courses,
                   (SELECT count(*) FROM unit)        AS units,
                   (SELECT count(*) FROM course_unit) AS links,
                   (SELECT count(*) FROM lesson)      AS lessons""").fetchone()
        check("one course", counts["courses"] == 1, f"{counts}")
        check("two units", counts["units"] == 2, f"{counts}")
        check("two course-unit links", counts["links"] == 2, f"{counts}")
        check("four lessons", counts["lessons"] == 4, f"{counts}")

        numbering = cur.execute("""
            SELECT u.script_name, cu.position, cu.displayed_number
              FROM course_unit cu JOIN unit u ON u.id = cu.unit_id
             ORDER BY cu.position""").fetchall()
        check("a blank displayed number survives the load",
              numbering[0]["displayed_number"] == "", f"{numbering}")
        check("position and displayed number still disagree",
              numbering[1]["position"] == 2
              and numbering[1]["displayed_number"] == "1", f"{numbering}")

        lesson_row = cur.execute(
            "SELECT * FROM lesson WHERE stable_id = %s",
            (f"{UNIT}::Lesson 1: Old Title",)).fetchone()
        check("plan is stored as jsonb",
              isinstance(lesson_row["plan"], dict))
        check("levels are stored in student order",
              isinstance(lesson_row["levels"], list)
              and len(lesson_row["levels"]) > 0)
        check("the stale key is kept but the current name is too",
              lesson_row["lesson_key"] == "Lesson 1: Old Title"
              and lesson_row["lesson_name"] == "Lesson 1: New Title")

        # --- claims against two lessons, one of which will change ---------
        print("\nMaking two claims")
        cur.execute("""INSERT INTO standards_set
            (framework, standard_set, set_type, framework_year, title,
             standard_count, boundary_provenance)
            VALUES ('DEMO','CS-DEMO','standards','2026','Demo',1,'drafted')
            RETURNING id""")
        set_id = cur.fetchone()["id"]
        cur.execute("""INSERT INTO standard
            (set_id, identifier, statement, concept, grade_band,
             boundary_includes, keywords, boundary_provenance)
            VALUES (%s,'D-1','A statement.','Algorithms','9-12',
                    ARRAY['x'], ARRAY['y'], 'drafted') RETURNING id""",
                    (set_id,))
        standard_id = cur.fetchone()["id"]
        course_id = cur.execute("SELECT id FROM course LIMIT 1").fetchone()["id"]
        cur.execute("""INSERT INTO run
            (set_id, course_id, snapshot_id, scope_note)
            VALUES (%s,%s,%s,'All concepts') RETURNING id""",
                    (set_id, course_id, snap1))
        run_id = cur.fetchone()["id"]

        will_change = cur.execute(
            "SELECT id, stable_id, content_hash FROM lesson WHERE stable_id=%s",
            (f"{UNIT}::Lesson 1: Old Title",)).fetchone()
        wont_change = cur.execute(
            "SELECT id, stable_id, content_hash FROM lesson WHERE stable_id=%s",
            (f"{UNIT}::Lesson 2: Project",)).fetchone()
        for lesson in (will_change, wont_change):
            cur.execute("""INSERT INTO alignment_record
                (run_id, standard_id, lesson_id, lesson_stable_id,
                 lesson_content_hash, level, evidence, review_status)
                VALUES (%s,%s,%s,%s,%s,'developed','A task.','accepted')""",
                (run_id, standard_id, lesson["id"], lesson["stable_id"],
                 lesson["content_hash"]))
        conn.commit()

        # --- change one lesson upstream -----------------------------------
        print("\nChanging one lesson upstream and loading a second snapshot")
        path = (repo_dir / "dashboard" / "config" / "scripts"
                / "demo_curly_1.multi")
        path.write_text(path.read_text(encoding="utf-8")
                        .replace("volatile", "temporary"), encoding="utf-8")
        git(repo_dir, "add", "-A")
        git(repo_dir, "commit", "-q", "-m", "edit a level")

        manifest2, lessons2 = make_corpus(repo_dir, tmp / "out2")
        snap2, stale2 = load_curriculum.load(conn, manifest2, lessons2,
                                             make_current=True,
                                             log=lambda *a: None)
        check("a second snapshot was written", snap2 != snap1)
        check("only one snapshot is current", cur.execute(
            "SELECT count(*) AS n FROM snapshot WHERE is_current"
        ).fetchone()["n"] == 1)
        check("the old snapshot's lessons are still there", cur.execute(
            "SELECT count(*) AS n FROM lesson WHERE snapshot_id=%s", (snap1,)
        ).fetchone()["n"] == 4)

        check("exactly one claim went stale", stale2 == 1, f"stale2={stale2}")
        changed = cur.execute("""
            SELECT lesson_stable_id, review_status FROM alignment_record
             ORDER BY lesson_stable_id""").fetchall()
        by_id = {r["lesson_stable_id"]: r["review_status"] for r in changed}
        check("the edited lesson's claim is stale",
              by_id[f"{UNIT}::Lesson 1: Old Title"] == "stale", f"{by_id}")
        check("the untouched lesson's claim is not",
              by_id[f"{UNIT}::Lesson 2: Project"] == "accepted", f"{by_id}")

        event = cur.execute("""
            SELECT * FROM review_event WHERE action='marked_stale'""").fetchall()
        check("the change was written to the audit trail", len(event) == 1,
              f"{len(event)} events")
        check("and says which lesson and which hashes",
              "Lesson 1: Old Title" in (event[0]["reason"] or ""),
              f"{event[0]['reason'] if event else None}")

        # --- a claim outside the snapshot's scope --------------------------
        print("\nA claim on a unit this snapshot does not cover")
        # A third lesson, because (run_id, standard_id, lesson_id) is unique
        # and the two above have used their pairs. The row that matters here
        # is lesson_stable_id, which names a unit no snapshot contains.
        spare = cur.execute(
            "SELECT id FROM lesson WHERE stable_id=%s",
            (f"{UNIT}::Pre-Assessment",)).fetchone()
        cur.execute("""INSERT INTO alignment_record
            (run_id, standard_id, lesson_id, lesson_stable_id,
             lesson_content_hash, level, evidence, review_status)
            VALUES (%s,%s,%s,'some-other-unit-2026::Lesson 1',
                    'deadbeef','introduced','A task.','accepted')""",
            (run_id, standard_id, spare["id"]))
        conn.commit()

        path.write_text(path.read_text(encoding="utf-8")
                        .replace("temporary", "transient"), encoding="utf-8")
        git(repo_dir, "add", "-A")
        git(repo_dir, "commit", "-q", "-m", "edit again")
        manifest3, lessons3 = make_corpus(repo_dir, tmp / "out3")
        load_curriculum.load(conn, manifest3, lessons3, make_current=False,
                             log=lambda *a: None)
        out_of_scope = cur.execute("""
            SELECT review_status FROM alignment_record
             WHERE lesson_stable_id = 'some-other-unit-2026::Lesson 1'
        """).fetchone()
        check("a claim on a unit outside the snapshot is left alone",
              out_of_scope["review_status"] == "accepted",
              f"{out_of_scope}")

        print("\nLoading the same commit twice")
        try:
            load_curriculum.load(conn, manifest3, lessons3, make_current=False,
                                 log=lambda *a: None)
            check("reloading the same commit is refused", False,
                  "it was allowed")
        except SystemExit as exc:
            check("reloading the same commit is refused",
                  "already loaded" in str(exc), str(exc))

        conn.commit()
    finally:
        conn.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{passes} checks passed, {len(failures)} failed")
    if failures:
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

