#!/usr/bin/env python3
"""Add v2 tables without altering or deleting legacy data. Explicit opt-in migration."""
import os
from pathlib import Path
import re
import sys

NAMES = ('instructional_inventory', 'performance_interpretation', 'evidence_run', 'evidence_review')


def sql():
    text = (Path(__file__).parents[2] / 'contract/tables.md').read_text()
    blocks = []
    for name in NAMES:
        match = re.search(r'CREATE TABLE ' + name + r' \(.*?\n\);', text, re.S)
        if not match:
            raise ValueError('Missing table definition: ' + name)
        blocks.append(match[0].replace('CREATE TABLE ', 'CREATE TABLE IF NOT EXISTS ', 1))
    return '\n\n'.join(blocks)


def main():
    if '--dry-run' in sys.argv:
        print(sql())
        return
    import psycopg
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.execute(sql())
    print('Evidence workflow tables ready. Legacy data unchanged.')


if __name__ == '__main__':
    main()
