"""Extracting the curriculum corpus from the upstream repository.

The upstream repository is read-only. Nothing in this package writes to it,
and nothing ever will.

    repo.py     reads blobs at one pinned commit, never a working tree
    levels.py   finds and reads student-facing level content, in both formats
    lessons.py  joins the unit file's tables into one record per lesson
    corpus.py   walks courses to units to lessons and emits the corpus
"""
