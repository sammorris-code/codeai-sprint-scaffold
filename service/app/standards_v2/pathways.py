"""Small DNF solver. Each clause is one possible route; clauses are alternatives.

No assumption that evidence on mutually exclusive routes can be combined.
The solver fails conservatively if a unusually large formula exceeds its budget.
"""


def join(left, right):
    if any(k in right and right[k] != v for k, v in left.items()):
        return None
    return {**left, **right}


def simplify(clauses):
    unique = {tuple(sorted(c.items())) for c in clauses}
    return [dict(c) for c in sorted(unique)
            if not any(set(other) < set(c) for other in unique)]


def universal(clauses, domains, budget=10000):
    """True/False, or None when the search limit prevents a conclusion."""
    remaining = [budget]

    def visit(current):
        remaining[0] -= 1
        if remaining[0] < 0:
            return None
        current = simplify(current)
        if {} in current:
            return True
        if not current:
            return False
        key = min({k for c in current for k in c}, key=lambda k: len(domains[k]))
        answers = []
        for option in domains[key]:
            answers.append(visit([{k: v for k, v in c.items() if k != key}
                                  for c in current if key not in c or c[key] == option]))
        return False if False in answers else None if None in answers else True

    if any(k not in domains or v not in domains[k] for c in clauses for k, v in c.items()):
        raise ValueError("Evidence names an unknown pathway")
    return visit(clauses)


def compatible(requirement_clauses, limit=10000):
    routes = [{}]
    for clauses in requirement_clauses:
        combined = []
        for route in routes:
            for clause in clauses:
                merged = join(route, clause)
                if merged is not None:
                    combined.append(merged)
                    if len(combined) > limit:
                        return None
        routes = simplify(combined)
        if not routes:
            return False
    return bool(routes)


def context(lessons, config=None):
    """Authored screen choices plus explicit course route overrides.

    Overrides may mark whole lessons/units as alternatives; no model guesses
    which lesson an alternate replaces. An unmapped alternate is optional.
    """
    config = config or {}
    domains = dict(config.get("domains", {}))
    if any(not isinstance(v, list) or len(v) < 2 or len(set(v)) != len(v)
           or not all(isinstance(x, str) and x for x in v) for v in domains.values()):
        raise ValueError("Pathway domains require at least two distinct string options")
    base, level_conditions, warnings = {}, {}, []
    lesson_ids = {l["stable_id"] for l in lessons}
    if set(config.get("lessons", {})) - lesson_ids:
        raise ValueError("Pathway configuration refers to unknown lessons")
    for lesson in lessons:
        lid = lesson["stable_id"]
        base[lid] = dict(config.get("lessons", {}).get(lid, {}))
        if any(k not in domains or v not in domains[k] for k, v in base[lid].items()):
            raise ValueError("Invalid lesson pathway override")
        if "alternate" in (lesson.get("lesson_group_name") or "").lower() and lid not in config.get("lessons", {}):
            key = f"unresolved-alternate:{lid}"
            domains[key] = ["take", "skip"]
            base[lid][key] = "take"
            warnings.append(f"{lid}: alternate progression has no explicit replacement mapping")
        levels = {l["level_name"]: l for l in lesson.get("levels") or []}
        groups = {}
        for name, level in levels.items():
            ctx = level.get("context") or {}
            if ctx.get("is_choice_option"):
                groups.setdefault(ctx.get("choice_parent") or "unresolved", []).append(name)
        for parent, options in groups.items():
            key = f"choice:{lid}:{parent}"
            if key in domains:
                raise ValueError("Course configuration cannot replace authored choice domains")
            parent_context = (levels.get(parent, {}).get("context") or {})
            optional = parent not in levels or parent_context.get("is_bonus")
            domains[key] = sorted(options) + (["__skip__"] if optional else [])
        for name, level in levels.items():
            conditions = dict(base[lid])
            ctx = level.get("context") or {}
            if ctx.get("is_choice_option"):
                conditions[f"choice:{lid}:{ctx.get('choice_parent') or 'unresolved'}"] = name
            if ctx.get("is_bonus"):
                key = f"bonus:{lid}:{name}"
                domains[key] = ["take", "skip"]
                conditions[key] = "take"
            level_conditions[(lid, name)] = conditions
        # A nested choice is available only on the route to its parent screen.
        def ancestors(name, seen):
            if name in seen:
                raise ValueError("Cycle in authored choice-parent metadata")
            own = level_conditions[(lid, name)]
            parent = (levels[name].get("context") or {}).get("choice_parent")
            if parent in levels:
                own = join(own, ancestors(parent, seen | {name}))
                if own is None:
                    raise ValueError("Contradictory nested choice metadata")
            return own
        for name in levels:
            level_conditions[(lid, name)] = ancestors(name, set())
    return {"domains": domains, "lessons": base, "levels": level_conditions, "warnings": warnings}
