"""The verification pass, and the aggregate outcome per standard.

The skill calls this mandatory, and it is the part that decides what survives.
Every claim is re-checked as if it were somebody else's work. Seven checks, in
the order the skill gives them.

These run **after** the model, in code, for a reason. Asking a model to mark
its own work is an assertion; a demotion that happens in a script is a rule.
Where a check needs judgement the model already supplied — did the student
task reach the standard's verb — the model reports the fact and this file
applies the consequence.
"""
import collections
import re

LEVELS = ("introduced", "developed", "mastered")
RANK = {level: i for i, level in enumerate(LEVELS)}

# A lesson carrying this many claims is re-examined. The skill says one to
# three is normal and six or more means most are exposure at best.
OVERCLAIM_AT = 6

# Evidence that points at nothing. These are the phrasings that mean "the
# lesson is about this topic", which the skill says is not evidence.
VAGUE = re.compile(
    r"^(the lesson|this lesson|students learn about|covers|discusses|"
    r"introduces the (topic|concept)|is about)\b", re.I)


def flag(kind, label, detail):
    return {"kind": kind, "label": label, "detail": detail}


def verify_lesson(claims, rejections, candidate_ids, lesson, distilled):
    """Re-check one lesson's claims. Returns (kept, dropped, flags-by-claim).

    Each claim comes back with `flags` attached and, where a check demanded it,
    a lower level than the model proposed.
    """
    kept, dropped = [], list(rejections)
    known = set(candidate_ids)
    choice_levels = {a["level"] for a in distilled.get("one_option_only", [])}

    for claim in claims:
        identifier = claim.get("standard_id")
        flags = []

        # 0. A standard that is not in the candidate set cannot be claimed.
        if identifier not in known:
            dropped.append({"standard_id": identifier, "kind": "not_a_candidate",
                            "reason": "Not in the candidate set for this run."})
            continue

        evidence = (claim.get("evidence") or "").strip()

        # 2. Evidence check. No pointable task, no claim.
        if len(evidence) < 12 or VAGUE.match(evidence):
            dropped.append({
                "standard_id": identifier, "kind": "no_evidence",
                "reason": f"Evidence does not name a student task: {evidence!r}"})
            continue

        level = claim.get("level", "introduced")
        if level not in RANK:
            level = "introduced"

        # 3. Cognitive verb check. Below the standard's verb is a demotion,
        #    not a rejection — the teaching is there, the depth is not.
        if not claim.get("cognitive_verb_match", True):
            if RANK[level] > 0:
                flags.append(flag("depth_doubt", "Lesson may not go deep enough",
                                  f"The student task sits below the standard's "
                                  f"cognitive verb, so this was lowered from "
                                  f"{level}."))
                level = LEVELS[RANK[level] - 1]
            else:
                flags.append(flag("depth_doubt", "Lesson may not go deep enough",
                                  "The student task sits below the standard's "
                                  "cognitive verb."))

        # 4. Artifact-type check. Kept with a stated caveat, never silently.
        if not claim.get("artifact_match", True):
            flags.append(flag("artifact_mismatch",
                              "The standard asks for a different artifact",
                              claim.get("note")
                              or "The lesson's artifact is a different kind "
                                 "from the one the standard names."))

        # 5. A choice-branch claim is met by a fraction of the class.
        in_choice = bool(claim.get("is_choice_level")) or \
            (claim.get("choice_option") in choice_levels)
        if in_choice:
            if RANK[level] > 0:
                flags.append(flag("weak_match", "Close match, likely not a real one",
                                  f"Evidence sits only in a choice branch, so "
                                  f"this was capped from {level} to introduced."))
            level = "introduced"

        kept.append({
            "standard_id": identifier,
            "level": level,
            "proposed_level": claim.get("level"),
            "evidence": evidence,
            "note": claim.get("note"),
            "is_choice_level": in_choice,
            "choice_option": claim.get("choice_option"),
            "flags": flags,
        })

    # 5b. Overclaim scan, once the survivors are known.
    if len(kept) >= OVERCLAIM_AT:
        for claim in kept:
            claim["flags"].append(flag(
                "overclaim", "This lesson carries many standards",
                f"{len(kept)} standards are claimed on one lesson. One to "
                f"three is normal; most of these are exposure at best."))

    # 6. Evidence-overlap annotation. Many-to-many is how crosscutting
    #    standards are meant to work, so both claims stay — but a reader must
    #    be able to see that one piece of student work is carrying both.
    by_evidence = collections.defaultdict(list)
    for claim in kept:
        by_evidence[claim["evidence"].lower()[:90]].append(claim["standard_id"])
    for identifiers in by_evidence.values():
        if len(identifiers) > 1:
            for claim in kept:
                if claim["standard_id"] in identifiers:
                    others = [i for i in identifiers
                              if i != claim["standard_id"]]
                    claim["note"] = ((claim["note"] + " ") if claim["note"] else "") \
                        + f"overlaps {', '.join(others)}"
    return kept, dropped


def aggregate(per_lesson_claims, per_lesson_rejections, candidate_ids):
    """One outcome per standard, including the misses.

    This is the table that lets the store answer "what percentage do you
    cover", which a mapping of matches alone cannot.
    """
    best = {}
    for claims in per_lesson_claims.values():
        for claim in claims:
            identifier = claim["standard_id"]
            if identifier not in best or \
                    RANK[claim["level"]] > RANK[best[identifier]]:
                best[identifier] = claim["level"]

    boundary_rejected = collections.Counter()
    for rejections in per_lesson_rejections.values():
        for rejection in rejections:
            if rejection.get("kind") == "boundary_exclusion":
                boundary_rejected[rejection["standard_id"]] += 1

    outcomes = {}
    for identifier in candidate_ids:
        if identifier in best:
            outcomes[identifier] = {"outcome": best[identifier], "rationale": None}
        elif boundary_rejected[identifier]:
            outcomes[identifier] = {
                "outcome": "boundary_issue",
                "rationale": f"Rejected on a boundary exclusion in "
                             f"{boundary_rejected[identifier]} lesson(s)."}
        else:
            outcomes[identifier] = {"outcome": "not_addressed", "rationale": None}
    return outcomes


def count_check(outcomes, candidate_ids):
    """Check 7, done by script rather than mental arithmetic.

    The six outcome values are exclusive and must sum to the candidate set.
    """
    counts = collections.Counter(o["outcome"] for o in outcomes.values())
    total = sum(counts.values())
    return {
        "candidate_set": len(candidate_ids),
        "counted": total,
        "balances": total == len(candidate_ids),
        "by_outcome": dict(counts),
    }


def coverage(outcomes):
    addressed = sum(1 for o in outcomes.values()
                    if o["outcome"] in LEVELS)
    total = len(outcomes) or 1
    return {"addressed": addressed, "total": len(outcomes),
            "percent": round(100 * addressed / total)}
