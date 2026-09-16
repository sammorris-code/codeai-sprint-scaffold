"""Forward alignment: given this curriculum, which standards does it address?

    engine.py   the candidate set, the prompt, and the one model call
    verify.py   the seven verification checks, and the aggregate outcome

The rules these files implement are not invented here. They come from the
`csta-alignment` skill, which is the written record of how this judgement is
made: four rating levels, evidence that points at a student task, boundaries
that defend against vocabulary matches, and a verification pass run as if the
claims were somebody else's work.

Two things this package does that the skill could not. It reads a structured
corpus, so the student actions and the choice branches are already marked
rather than inferred from a document dump. And it writes to a store, so a
claim carries the lesson hash it was made against and goes stale by itself.
"""
