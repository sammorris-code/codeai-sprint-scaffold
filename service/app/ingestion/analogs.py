"""The gate on `nearest_csta`.

A bare identifier is an assertion, and nothing can test an assertion. The first
version of this field asked the model for identifiers and stored whatever came
back. On a 55-standard Oklahoma run, 80% of standards came back with an analog,
against a prompt that says in as many words that most state standards have none
and that an empty list is the expected answer. Rewording the prompt a third time
was not going to close that gap.

So the model is now asked for the evidence instead of the conclusion: if a CSTA
standard's boundary wording was worth adapting, quote the span you adapted. A
quote is checkable, and this file checks it.

Three things have to hold, and an analog failing any of them is dropped:

1. The span is long enough to mean something. A one-word "quote" like
   "abstraction" is a substring of half the reference and proves nothing.
2. The span really is in the CSTA standard it is credited to. This is the check
   that cannot be gamed by quoting the boundary back at itself.
3. The span left a mark on the boundary that was written. A standard whose
   wording was adapted shows up in the wording; one that was listed does not.

What survives is stored exactly as before - a `text[]` of identifiers. This
file changes how trustworthy that array is, not its shape, so nothing
downstream of ingestion has to know the gate exists.
"""
import math
import re

# The span must carry at least this many content words. Below it, a match
# against the reference is coincidence rather than a quotation.
MIN_SPAN_WORDS = 3

# Of the span's content words, how many must survive into a single boundary
# line. Adaptation legitimately rewrites words - that is what adaptation is -
# so this is deliberately forgiving. It is set to catch "borrowed nothing", not
# to police the rewrite. The count is capped so a long span is not held to a
# higher standard than a short one.
MIN_SHARED_WORDS = 2
MAX_SHARED_WORDS = 3
SHARED_FRACTION = 0.5

_STOPWORDS = {
    "and", "the", "for", "that", "with", "this", "from", "are", "was", "were",
    "can", "will", "would", "should", "must", "have", "has", "had", "its",
    "their", "them", "they", "not", "but", "how", "why", "what", "when",
    "which", "who", "whom", "into", "onto", "than", "then", "there", "here",
    "such", "some", "any", "all", "each", "both", "other", "more", "most",
    "own", "same", "only", "also", "about", "over", "under", "between",
    "using", "used", "use", "uses", "including", "include", "includes",
    "student", "students", "learner", "learners",
}


def normalize(text):
    """Lowercase, and every run of non-letters becomes one space.

    Punctuation drifts when a person or a model quotes something - a trailing
    comma, a curly apostrophe, a line break mid-phrase. None of that changes
    whether the words were taken from the source, so none of it should decide
    the check.
    """
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def content_words(text):
    """The words worth comparing: no stopwords, nothing under three letters."""
    return [w for w in normalize(text).split()
            if len(w) > 2 and w not in _STOPWORDS]


def shared_needed(span_words):
    """How many of a span's content words must reach the boundary."""
    return max(MIN_SHARED_WORDS,
               min(MAX_SHARED_WORDS,
                   math.ceil(SHARED_FRACTION * len(span_words))))


def reject(adapted, csta_text, boundary_lines):
    """Why this analog should be dropped, or None to keep it.

    Returns a reason written for a person reading an ingest report, not a code.
    """
    words = content_words(adapted)
    if len(words) < MIN_SPAN_WORDS:
        return "quoted span too short to check"

    if not csta_text:
        # The reference did not carry this standard's text. Refusing here would
        # punish the drafter for a gap in our own files, so the analog is kept
        # and the gap is named.
        return None

    if normalize(adapted) not in normalize(csta_text):
        return "quoted span is not in the CSTA standard it credits"

    needed = shared_needed(words)
    for line in boundary_lines:
        line_words = set(content_words(line))
        if sum(1 for w in set(words) if w in line_words) >= needed:
            return None
    return "quoted span left no trace in the boundary that was written"


def apply_gate(boundary, csta_texts):
    """Drop the analogs that do not hold up. Returns their reasons.

    Mutates `boundary.analogs` in place, which is what makes the stored
    `nearest_csta` array honest without anything downstream changing.
    """
    lines = list(boundary.boundary_includes) + list(boundary.boundary_excludes)
    kept, dropped = [], []
    for analog in boundary.analogs:
        reason = reject(analog.adapted, csta_texts.get(analog.identifier), lines)
        if reason is None:
            kept.append(analog)
        else:
            dropped.append((analog.identifier, reason))
    boundary.analogs = kept
    return dropped
