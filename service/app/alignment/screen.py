"""Tier 0: a free lexical screen. **Measured, and it does not work.**

Keep this module for the measurement, not for the screen. `measure_screen.py`
is the reusable part; the conclusion below is why nothing calls `shortlist()`
in the pipeline.

The idea was sound. A lesson is judged against every standard in the set and
one to three land, so ~95 of every 100 pairs are a no-match and paying a model
to say so is where the money goes. A free screen that drops the pairs sharing
no vocabulary should remove most of that work.

**It does not, and here is the measurement.** 148 AIF lessons, 55 Oklahoma
standards, 8,140 pairs, against 361 pairs a person claimed and 198 this
pipeline claimed:

    top N per lesson    pairs seen    human recall    model recall
              10           18%            53%             66%
              20           36%            72%             77%
              30           55%            86%             87%
              40           73%            93%             97%

To keep 95% of human claims you must look at three quarters of the pairs. That
is a 27% saving for a 5% loss of claims a person actually made — and the reason
this cascade was proposed was to *raise* recall, not trade it away.

A global threshold is worse: the largest cut that loses no human claim keeps
99.3% of pairs.

**Why.** Alignment is semantic, not lexical. A standard about evaluating an
artifact for accessibility belongs on a lesson about user testing, and the two
share almost no vocabulary. Meanwhile a lesson carries ~430 distinct terms and
a standard ~90, so *some* overlap is certain — the first version of this scored
raw overlap and kept 99% of pairs at every threshold, because `build`, `change`
and `apply` appear in half the lessons and most standards. Weighting by inverse
document frequency fixed that and separated the medians (28.8 for human-claimed
pairs against 16.2 for all pairs), but the distributions still overlap far too
much to cut between.

**What follows from it.** A cheap *model* can screen on meaning where a keyword
cannot. If the cascade is built, tier 1 should be Haiku or Sonnet reading the
lesson, not this. Building this first was still right: it cost nothing and it
ruled out the free option with evidence instead of opinion.
"""
import math
import re

STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "have", "has", "are",
    "was", "were", "will", "can", "may", "not", "but", "you", "your", "their",
    "them", "they", "its", "it's", "how", "what", "when", "which", "who", "why",
    "use", "used", "using", "into", "about", "over", "such", "these", "those",
    "than", "then", "also", "each", "other", "some", "more", "most", "one",
    "two", "student", "students", "lesson", "level", "levels", "activity",
    "teacher", "class", "work", "make", "made", "take", "give", "different",
    "example", "examples", "include", "including", "based", "within", "between",
    "should", "would", "could", "must", "need", "needs", "identify", "describe",
    "explain", "discuss", "understand", "learn", "know", "able",
}

WORD = re.compile(r"[a-z][a-z0-9'\-]{2,}")
TAG = re.compile(r"<[^>]+>")


def stem(word):
    """Crude suffix stripping. Good enough for a screen, and no dependency."""
    for suffix in ("ation", "ations", "tion", "tions", "ing", "ers", "er",
                   "ies", "ied", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def terms(text):
    """Distinct stemmed content words."""
    if not text:
        return set()
    plain = TAG.sub(" ", str(text)).lower()
    return {stem(w) for w in WORD.findall(plain) if w not in STOPWORDS}


def lesson_terms(lesson):
    """Everything the lesson says, teacher-facing and student-facing.

    Deliberately wide. A standard that appears only in a discussion prompt in
    the teaching guide is still a candidate, and the distilled record would
    have dropped that prompt as choreography.
    """
    plan = lesson.get("plan") or {}
    parts = [lesson.get("lesson_name"), lesson.get("unit_name")]
    parts += plan.get("objectives") or []
    for key in ("overview_md", "student_overview_md", "purpose_md",
                "preparation_md", "assessment_opportunities_md"):
        parts.append(plan.get(key))
    for entry in plan.get("vocabulary") or []:
        parts += [entry.get("word"), entry.get("definition")]
    for activity in plan.get("activities") or []:
        for section in activity.get("sections") or []:
            parts += [section.get("name"), section.get("progression_name"),
                      section.get("description_md"), section.get("remarks_md")]
            for tip in section.get("tips") or []:
                if isinstance(tip, dict):
                    parts.append(tip.get("markdown"))
    for level in lesson.get("levels") or []:
        parts += [level.get("title"), level.get("student_text")]
        for option in level.get("answer_options") or []:
            parts.append(option.get("text"))

    out = set()
    for part in parts:
        out |= terms(part)
    return out


def standard_terms(standard):
    """The standard's own vocabulary, weighted by where it came from.

    Keywords are retrieval terms and exist for exactly this job, so they carry
    most. The boundary prose is long and mostly ordinary English, so it carries
    least — it is included because a lesson that trips an exclusion is related
    enough to be worth judging, and dropping it here would hide the rejection a
    reviewer needs to see.
    """
    weighted = {}

    def add(text, weight):
        for term in terms(text):
            weighted[term] = max(weighted.get(term, 0), weight)

    for keyword in (standard.get("keywords") or []):
        add(keyword, 3.0)
    add(standard.get("statement"), 2.0)
    add(standard.get("concept"), 1.0)
    add(standard.get("subconcept"), 1.0)
    for text in (standard.get("boundary_includes") or []):
        add(text, 0.5)
    for text in (standard.get("boundary_excludes") or []):
        add(text, 0.5)
    return weighted


def build_idf(lesson_word_sets):
    """How rare each term is across the curriculum.

    This is the whole trick. A standard has about 90 terms and a lesson about
    430, so *some* overlap is certain: the first version of this screen scored
    on raw overlap and kept 99% of pairs at every threshold, because words like
    `build`, `change`, `check` and `apply` appear in half the lessons and in
    most standards.

    Weighting by inverse document frequency makes those terms worth nothing and
    leaves the signal in the rare ones — `cybersecurity`, `flowchart`,
    `recursion`, `packet`. A term in every lesson scores 0. A term in one
    lesson scores high.
    """
    total = len(lesson_word_sets) or 1
    frequency = {}
    for words in lesson_word_sets:
        for term in words:
            frequency[term] = frequency.get(term, 0) + 1
    return {term: math.log(total / count)
            for term, count in frequency.items()}


def score(lesson_words, standard_weights, idf):
    """Shared vocabulary, discounted by how ordinary each word is."""
    total = 0.0
    matched = []
    for term, weight in standard_weights.items():
        if term in lesson_words:
            contribution = weight * idf.get(term, 0.0)
            if contribution > 0:
                total += contribution
                matched.append(term)
    return total, matched


def shortlist(lesson, standards, idf, threshold, cache=None, top_n=None):
    """The standards worth judging for this lesson.

    Returns (kept, dropped) as lists of (identifier, score). `top_n` caps the
    shortlist regardless of threshold, which is what bounds the cost of the
    tier that follows.
    """
    words = lesson_terms(lesson)
    scored = []
    for standard in standards:
        identifier = standard["identifier"]
        if cache is not None:
            weights = cache.setdefault(identifier, standard_terms(standard))
        else:
            weights = standard_terms(standard)
        total, _ = score(words, weights, idf)
        scored.append((identifier, total))
    scored.sort(key=lambda pair: -pair[1])

    kept = [pair for pair in scored if pair[1] >= threshold]
    if top_n is not None and len(kept) > top_n:
        kept = kept[:top_n]
    keep_ids = {identifier for identifier, _ in kept}
    dropped = [pair for pair in scored if pair[0] not in keep_ids]
    return kept, dropped
