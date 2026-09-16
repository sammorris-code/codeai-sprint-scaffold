#!/usr/bin/env python3
"""Measure the tier-0 screen against claims a human actually made.

    python3 service/measure_screen.py --set 3 --csv mapping.csv

The screen decides which (lesson, standard) pairs a model never sees. A pair it
drops is invisible afterwards, so the only number that matters is **recall**:
of the pairs a person claimed, how many survive?

Precision is not the goal here and a low figure is expected. The screen's job
is to remove the pairs that share no vocabulary at all, not to guess which
survivors are real.

Two reference sets, and they answer different questions:

  the hand mapping   369 pairs a person claimed. Recall against this is the
                     safety number — anything dropped here is a claim a human
                     made and the pipeline would never reach.
  the model run      198 pairs this pipeline claimed with evidence. Recall
                     against this says whether the screen would have changed
                     the answer we already have.

The output is a curve, not a verdict. Pick the threshold from it.
"""
import argparse
import collections
import csv
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import psycopg                                                    # noqa: E402
from psycopg.rows import dict_row                                 # noqa: E402

from service.app.alignment import screen                          # noqa: E402
from service.import_legacy import corpus_index, resolve           # noqa: E402

DSN = os.environ.get("DATABASE_URL",
                     "postgresql://standards:standards@localhost:5432/standards")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure the tier-0 screen.")
    ap.add_argument("--set", type=int, required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--snapshot", type=int, default=None)
    ap.add_argument("--runs", default="", help="run ids to also check, e.g. 3,4")
    ap.add_argument("--max-threshold", type=int, default=12)
    args = ap.parse_args(argv)

    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        snapshot_id = args.snapshot or conn.execute(
            "SELECT id FROM snapshot WHERE is_current").fetchone()["id"]

        standards = conn.execute("""
            SELECT identifier, statement, concept, subconcept, grade_band,
                   boundary_includes, boundary_excludes, keywords
              FROM standard WHERE set_id = %s AND hierarchy_role <> 'umbrella'
             ORDER BY id""", (args.set,)).fetchall()

        lessons = conn.execute("""
            SELECT DISTINCT l.id, l.stable_id, l.lesson_name, l.plan, l.levels
              FROM lesson l
             WHERE l.snapshot_id = %s AND l.has_lesson_plan""",
            (snapshot_id,)).fetchall()
        by_stable = {l["stable_id"]: l for l in lessons}

        # --- the human claims ------------------------------------------
        by_token, by_taught, _ = corpus_index(conn, snapshot_id)
        text = pathlib.Path(args.csv).read_text(encoding="utf-8-sig")
        human, unresolved = set(), 0
        for row in csv.DictReader(text.splitlines()):
            lesson, _ = resolve(row, by_token, by_taught)
            if lesson is None or lesson["stable_id"] not in by_stable:
                unresolved += 1
                continue
            human.add((lesson["stable_id"], row["standard_id"]))

        # --- our own claims --------------------------------------------
        model = set()
        run_ids = [int(r) for r in args.runs.split(",") if r.strip()]
        if run_ids:
            for row in conn.execute("""
                SELECT ar.lesson_stable_id, s.identifier
                  FROM alignment_record ar JOIN standard s ON s.id = ar.standard_id
                 WHERE ar.run_id = ANY(%s)""", (run_ids,)).fetchall():
                if row["lesson_stable_id"] in by_stable:
                    model.add((row["lesson_stable_id"], row["identifier"]))

    print(f"Standards : {len(standards)}")
    print(f"Lessons   : {len(lessons)} taught")
    print(f"All pairs : {len(standards) * len(lessons):,}")
    print(f"Human claims resolved: {len(human)}"
          + (f"  ({unresolved} rows could not be resolved)" if unresolved else ""))
    if model:
        print(f"Model claims         : {len(model)}")

    # Score every pair once, then read the curve off the scores.
    weights = {s["identifier"]: screen.standard_terms(s) for s in standards}
    print("\nScoring every pair...", end="", flush=True)
    lesson_words = {l["stable_id"]: screen.lesson_terms(l) for l in lessons}
    idf = screen.build_idf(list(lesson_words.values()))
    scores = {}
    for stable_id, words in lesson_words.items():
        for identifier, weight_map in weights.items():
            total, _ = screen.score(words, weight_map, idf)
            scores[(stable_id, identifier)] = total
    print(" done")

    import statistics
    human_scores = sorted(scores[p] for p in human if p in scores)
    all_scores = sorted(scores.values())
    print(f"\nScore separation (this is what decides whether a screen exists):")
    print(f"  all pairs      median {statistics.median(all_scores):6.1f}  "
          f"90th pct {all_scores[int(.9*len(all_scores))]:6.1f}")
    print(f"  human-claimed  median {statistics.median(human_scores):6.1f}  "
          f"10th pct {human_scores[int(.1*len(human_scores))]:6.1f}")

    total_pairs = len(scores)
    print(f"\n{'threshold':>9} | {'pairs kept':>11} {'of all':>7} | "
          f"{'human recall':>13} | {'model recall':>12}")
    print("-" * 66)
    rows = []
    steps = [round(x * 0.5, 1) for x in range(0, args.max_threshold * 2 + 1)]
    for threshold in steps:
        kept = {pair for pair, value in scores.items() if value >= threshold}
        human_kept = len(human & kept)
        model_kept = len(model & kept) if model else 0
        row = {
            "threshold": threshold,
            "kept": len(kept),
            "kept_pct": 100 * len(kept) / total_pairs,
            "human_recall": 100 * human_kept / len(human) if human else 0,
            "model_recall": 100 * model_kept / len(model) if model else 0,
            "human_lost": len(human) - human_kept,
            "model_lost": len(model) - model_kept,
        }
        rows.append(row)
        print(f"{threshold:>9.1f} | {row['kept']:>11,} {row['kept_pct']:>6.1f}% | "
              f"{row['human_recall']:>11.1f}% ({row['human_lost']:>3} lost) | "
              f"{row['model_recall']:>10.1f}%"
              + (f" ({row['model_lost']:>3} lost)" if model else ""))

    # The useful threshold is the largest one that loses nothing a human claimed.
    safe = max((r for r in rows if r["human_lost"] == 0),
               key=lambda r: r["threshold"], default=None)
    if safe:
        print(f"\nLargest threshold that loses no human claim: {safe['threshold']}")
        print(f"  keeps {safe['kept']:,} of {total_pairs:,} pairs "
              f"({safe['kept_pct']:.1f}%)")
        print(f"  a model would see "
              f"{safe['kept']/max(1,len(lessons)):.1f} standards per lesson "
              f"instead of {len(standards)}")
        print(f"  that is {100 - safe['kept_pct']:.0f}% of the work removed "
              f"for nothing")

    cut = safe["threshold"] if safe else 1
    print(f"\nWhat the screen drops just above the safe threshold ({cut + 0.5}):")
    lost = [pair for pair in human if scores.get(pair, 0) < cut + 0.5]
    if not lost:
        print("  nothing")
    for stable_id, identifier in sorted(lost)[:10]:
        print(f"  {identifier:16} on {stable_id.split('::')[-1][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
