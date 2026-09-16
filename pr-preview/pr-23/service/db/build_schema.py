#!/usr/bin/env python3
"""Builds db/schema.sql out of contract/tables.md.

The tables are documented with their reasons in contract/tables.md, and that
document holds complete CREATE statements. Copying them into a second file by
hand would guarantee the two drift apart, and a schema that disagrees with its
own documentation is worse than no documentation.

So the document is the source. This reads the SQL blocks out of it, in order,
and writes the file Postgres actually runs.

    python3 service/db/build_schema.py          write service/db/schema.sql
    python3 service/db/build_schema.py --check  fail if it is out of date
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "contract" / "tables.md"
TARGET = ROOT / "service" / "db" / "schema.sql"

HEADER = """-- GENERATED FILE. DO NOT EDIT.
--
-- Built from contract/tables.md by service/db/build_schema.py.
-- Change the tables there, with the reason for the change, then re-run:
--
--     python3 service/db/build_schema.py
--
-- CI fails if this file and that document disagree.

"""


def build():
    text = SOURCE.read_text()
    blocks = re.findall(r"```sql\n(.*?)```", text, re.DOTALL)
    ddl = [b.strip() for b in blocks if re.search(r"\bCREATE\b", b, re.I)]
    if not ddl:
        sys.exit("No CREATE statements found in " + str(SOURCE))
    return HEADER + "\n\n".join(ddl) + "\n"


def main():
    built = build()
    if "--check" in sys.argv:
        if not TARGET.exists():
            sys.exit("schema.sql is missing. Run: python3 service/db/build_schema.py")
        if TARGET.read_text() != built:
            sys.exit("schema.sql is out of date with contract/tables.md.\n"
                     "Run: python3 service/db/build_schema.py")
        print("schema.sql matches contract/tables.md")
        return
    TARGET.write_text(built)
    tables = re.findall(r"CREATE TABLE (\w+)", built)
    print(f"Wrote {TARGET.relative_to(ROOT)} - {len(tables)} tables: {', '.join(tables)}")


if __name__ == "__main__":
    main()
