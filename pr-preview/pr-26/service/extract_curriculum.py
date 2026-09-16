#!/usr/bin/env python3
"""Extract the curriculum corpus from a clone of the upstream repository.

    python3 service/extract_curriculum.py --repo ./cdo --out ./out --courses aif

The upstream repository is read-only. This reads it and writes nothing to it.

**Get the clone like this.** Shallow, and with no blob filter:

    git clone --depth 1 --no-checkout -b staging \\
      https://github.com/code-dot-org/code-dot-org.git cdo

That is about 280 MB and takes a couple of minutes. Two parts of it matter.

`--no-checkout`, because there is no working tree to check out into. Level file
names contain `:` and `?`, which Windows forbids, so `git checkout` refuses 512
paths, abandons the whole `levels/` directory, and still exits 0. Everything
here is read out of git object storage instead, which sidesteps the filesystem
entirely and reads the same on every machine.

No `--filter=blob:none`, because a blobless clone fetches each blob on demand,
and the demand here is a hundred thousand small files one at a time. Fetching
them in one pack up front is the difference between seconds and hours.

**This does both halves of the extraction in one run** — the lesson plans a
teacher reads and the level screens a student reads. They used to be two
commands. They are one because a corpus with plans and no student instructions
is the exact undercount this pipeline exists to prevent, and a separate second
command is a thing that can be skipped.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from service.app.curriculum import corpus            # noqa: E402
from service.app.curriculum.repo import Repo         # noqa: E402

# Named course sets, so nobody has to remember a slug. These are a convenience,
# not configuration: any course key in dashboard/config/courses/ can be passed
# directly, and extending to CSD or CSP is this list plus nothing.
COURSE_SETS = {
    "aif": [
        "ai-foundations-exploring-ai-and-cs-2026",
        "ai-foundations-designing-and-building-with-ai-2026",
        "ai-foundations-year1-2026",
    ],
    "aid": [
        "ai-discoveries-2026",
    ],
}


def resolve_courses(values):
    out = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            for key in COURSE_SETS.get(part, [part]):
                if key not in out:
                    out.append(key)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract the curriculum corpus. Reads upstream, never writes it.")
    ap.add_argument("--repo", required=True,
                    help="path to the code-dot-org clone")
    ap.add_argument("--out", required=True,
                    help="directory to write the corpus into")
    ap.add_argument("--courses", nargs="+", default=["aif"],
                    help="course keys, or a named set: "
                         + ", ".join(sorted(COURSE_SETS)))
    ap.add_argument("--rev", default="HEAD",
                    help="commit to extract (default HEAD)")
    ap.add_argument("--cache-dir", default=None,
                    help="where to keep the level-name index between runs "
                         "(default: <out>/.cache)")
    args = ap.parse_args(argv)

    course_keys = resolve_courses(args.courses)
    cache_dir = args.cache_dir or str(pathlib.Path(args.out) / ".cache")

    print(f"Extracting {len(course_keys)} courses from {args.repo}")
    for key in course_keys:
        print(f"  - {key}")

    with Repo(args.repo, args.rev) as repo:
        print(f"  commit: {repo.commit}")
        result = corpus.extract(repo, course_keys, cache_dir=cache_dir)
        manifest = corpus.write(result, args.out)

    print("\nTotals")
    for key, value in manifest["totals"].items():
        label = key.replace("_", " ").capitalize()
        print(f"  {label:34} {value:>10,}")

    warnings = result["warnings"]
    if warnings:
        kinds = {}
        for w in warnings:
            kinds[w["kind"]] = kinds.get(w["kind"], 0) + 1
        print(f"\n{len(warnings)} warnings, in warnings.json")
        for kind, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
            print(f"  {kind:34} {n:>10,}")
    else:
        print("\nNo warnings.")

    # A silent extraction gap poisons everything downstream, so say the thing
    # that would otherwise have to be noticed.
    missing = sum(1 for w in warnings if w["kind"] == "missing_level")
    if missing:
        print(f"\n{missing} level references did not resolve. That is an "
              f"undercount, not a curiosity. Check warnings.json before "
              f"using this corpus as evidence.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
