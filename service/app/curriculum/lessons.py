"""Turning one unit file into one record per lesson.

A `.script_json` file is not a nested lesson plan. It is a relational dump —
fourteen flat tables joined by `seeding_key` — because that is what the
seeding task needs to write into MySQL. The teaching structure a reviewer
cares about has to be rebuilt from it:

    lesson
      -> lesson_activity        (seeding_key.lesson.key)
        -> activity_section     (seeding_key.lesson_activity.key)
          -> script_level       (seeding_key.activity_section.key)
            -> level            (level_keys, resolved by levels.py)

Three things here are easy to get wrong and are handled explicitly.

**`lesson.key` is often a former title.** Authors key a lesson with its name
at the moment of creation — `'Lesson 5: Making Decisions with If/Else'` — and
the key does not follow a rename. So the key is opaque: join on it, never
display it, and never parse a lesson number out of it. `lesson_name` is what a
person should see, and `lesson_token` is derived from the name, not the key.

**A lesson with no plan is still a lesson.** Pre-assessments, end-of-unit
assessments and surveys carry `has_lesson_plan: false`. They hold a position
in the sequence, which is why `relative_position` and `absolute_position`
disagree. They are kept, flagged, and never given an inferred objective.

**`content_hash` covers the content and nothing else.** No timestamps, no
paths, no provenance. The unit's own `serialized_at` cannot do this job: one
edited section restamps the whole unit, so it cannot say which lesson changed.
The hash covers the student instructions as well as the plan, because evidence
for an alignment claim is drawn from both — a claim should go stale when the
screens a student reads change, not only when the teacher's notes do.
"""
import csv
import hashlib
import io
import json
import posixpath
import re

from .repo import SUBDIRS

LESSON_NUMBER = re.compile(r"^\s*lesson\s+(\d+)\b", re.I)
NON_TOKEN = re.compile(r"[^a-z0-9]+")


def lesson_token(lesson_name, fallback_position):
    """The bare token a viewer renders as a `unit.lesson` pill.

    No `L` prefix. Numeric where the lesson is numbered; otherwise a short
    slug such as `capstone` or `pre-assessment`, which is allowed and must
    sort after every numeric token.
    """
    m = LESSON_NUMBER.match(lesson_name or "")
    if m:
        return m.group(1)
    slug = NON_TOKEN.sub("-", (lesson_name or "").lower()).strip("-")
    return slug or str(fallback_position)


def slugify(text, limit=60):
    return NON_TOKEN.sub("-", (text or "").lower()).strip("-")[:limit] or "lesson"


def content_hash(payload):
    """Stable fingerprint of content. Key order is forced so the same content
    hashes the same on every machine and every run."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


class StandardsCatalog:
    """The frameworks the curriculum already cites, resolved to statement text.

    The curriculum carries its authors' own standard claims. They are a strong
    prior and a useful cross-check — and they can be wrong in both directions,
    so they are recorded as claims, never as evidence.
    """

    def __init__(self, repo):
        self.by_framework = {}
        self.layouts = {}
        for path in repo.list("standards", suffixes=("_standards.csv",)):
            short = posixpath.basename(path)[:-len("_standards.csv")]
            # utf-8-sig: these exports carry a byte-order mark often enough
            # that ignoring it corrupts the first column's name.
            text = repo.read(path).decode("utf-8-sig", "replace")
            reader = csv.DictReader(io.StringIO(text))
            fields = reader.fieldnames or []

            # These files do not share a layout. `csta2026` is
            # framework,category,standard,description — the code is in
            # `standard` and `category` holds the concept. `ai4k12-2021` is
            # framework,parent,name,category,description,type — the code is in
            # `category`. Picking one and hoping resolves nothing, silently,
            # which is how 607 citations came back unresolved the first time.
            code_field = "standard" if "standard" in fields else "category"
            concept_field = "category" if code_field == "standard" else "name"
            self.layouts[short] = code_field

            table = {}
            for row in reader:
                code = (row.get(code_field) or "").strip()
                if code:
                    table[code] = {
                        "statement": (row.get("description") or "").strip(),
                        "concept": (row.get(concept_field) or "").strip(),
                        "type": (row.get("type") or "").strip(),
                    }
            self.by_framework[short] = table

    def resolve(self, framework, shortcode):
        entry = (self.by_framework.get(framework) or {}).get(shortcode)
        return {
            "framework": framework,
            "shortcode": shortcode,
            "statement": entry["statement"] if entry else None,
            "concept": entry["concept"] if entry else None,
            "resolved": entry is not None,
        }


def _group(rows, key_path):
    """Index rows by a dotted field inside their seeding_key."""
    out = {}
    for row in rows or []:
        val = (row.get("seeding_key") or {}).get(key_path)
        if val is not None:
            out.setdefault(val, []).append(row)
    return out


def extract_unit(repo, script_name, level_index, catalog):
    """Every lesson in one unit, plus the warnings the run should report."""
    path = f"{SUBDIRS['units']}/{script_name}.script_json"
    doc = json.loads(repo.read_text(path))

    unit = doc.get("script") or {}
    props = unit.get("properties") or {}
    unit_name = props.get("title") or props.get("display_name") or script_name

    activities_by_lesson = _group(doc.get("lesson_activities"), "lesson.key")
    sections_by_activity = _group(doc.get("activity_sections"), "lesson_activity.key")
    sls_by_section = _group(doc.get("script_levels"), "activity_section.key")
    objectives_by_lesson = _group(doc.get("objectives"), "lesson.key")
    standards_by_lesson = _group(doc.get("lessons_standards"), "lesson.key")
    opp_by_lesson = _group(doc.get("lessons_opportunity_standards"), "lesson.key")
    resources_by_lesson = _group(doc.get("lessons_resources"), "lesson.key")
    vocab_by_lesson = _group(doc.get("lessons_vocabularies"), "lesson.key")

    resources = {r.get("key"): r for r in (doc.get("resources") or [])}
    vocab = {v.get("key"): v for v in (doc.get("vocabularies") or [])}

    warnings = []
    lessons = []

    for row in doc.get("lessons") or []:
        key = row.get("key")
        name = row.get("name") or key
        lprops = row.get("properties") or {}
        has_plan = bool(row.get("has_lesson_plan"))

        # --- the teaching structure, and the levels hanging off it ---------
        activities = []
        level_records = []
        duration = 0
        seen_levels = set()

        for act in sorted(activities_by_lesson.get(key, []),
                          key=lambda a: a.get("position") or 0):
            sections = []
            for sec in sorted(sections_by_activity.get(act.get("key"), []),
                              key=lambda s: s.get("position") or 0):
                sp = sec.get("properties") or {}
                if sp.get("duration"):
                    try:
                        duration += int(sp["duration"])
                    except (TypeError, ValueError):
                        pass

                section_levels = []
                for sl in sorted(sls_by_section.get(sec.get("key"), []),
                                 key=lambda x: (x.get("activity_section_position") or 0,
                                                x.get("position") or 0)):
                    for level_name in sl.get("level_keys") or []:
                        section_levels.append(level_name)
                        # Expand parents into children here. A parent holds no
                        # text of its own; skipping this loses most of the
                        # student words without reporting anything.
                        for lvl, ctx in level_index.expand(level_name):
                            if lvl is None:
                                warnings.append({
                                    "kind": "missing_level",
                                    "script_name": script_name,
                                    "lesson_key": key,
                                    "level_name": ctx.get("missing_level_name"),
                                })
                                continue
                            if lvl.name in seen_levels:
                                continue
                            seen_levels.add(lvl.name)
                            rec = lvl.as_record()
                            rec["context"] = {
                                "activity_position": act.get("position"),
                                "section_position": sec.get("position"),
                                "section_name": sp.get("name"),
                                "progression_name": sp.get("progression_name")
                                or (sl.get("properties") or {}).get("progression"),
                                "is_assessment": bool(sl.get("assessment")),
                                "is_bonus": bool(sl.get("bonus")),
                                "is_choice_option": ctx.get("is_choice_option", False),
                                "choice_parent": ctx.get("choice_parent"),
                            }
                            level_records.append(rec)

                sections.append({
                    "position": sec.get("position"),
                    "name": sp.get("name"),
                    "progression_name": sp.get("progression_name"),
                    "description_md": sp.get("description"),
                    "tips": sp.get("tips") or [],
                    "is_remarks": bool(sp.get("remarks")),
                    "remarks_md": sp.get("remarks"),
                    "duration_minutes": sp.get("duration"),
                    "levels": section_levels,
                })
            activities.append({"position": act.get("position"),
                               "sections": sections})

        # --- alignment inputs ---------------------------------------------
        objectives = [
            (o.get("properties") or {}).get("description")
            for o in objectives_by_lesson.get(key, [])
        ]
        objectives = [o for o in objectives if o]

        def cited(rows):
            out = []
            for r in rows:
                sk = r.get("seeding_key") or {}
                fw, code = sk.get("framework.shortcode"), sk.get("standard.shortcode")
                if fw and code:
                    out.append(catalog.resolve(fw, code))
            return out

        standards = cited(standards_by_lesson.get(key, []))
        opportunity = cited(opp_by_lesson.get(key, []))

        # A citation that does not resolve to statement text is a gap, not a
        # detail. These are the authors' own claims and the strongest prior a
        # reviewer has; an unresolved one is a claim nobody can read.
        for s in standards + opportunity:
            if not s["resolved"]:
                warnings.append({
                    "kind": "unresolved_standard_citation",
                    "script_name": script_name,
                    "lesson_key": key,
                    "framework": s["framework"],
                    "shortcode": s["shortcode"],
                })

        lesson_resources = []
        for r in resources_by_lesson.get(key, []):
            rk = (r.get("seeding_key") or {}).get("resource.key")
            src = resources.get(rk)
            if not src:
                continue
            rprops = src.get("properties") or {}
            lesson_resources.append({
                "name": src.get("name"),
                "url": src.get("url"),
                "audience": rprops.get("audience"),
                # 133 linked documents across the corpus are answer keys
                # restricted to verified teachers. The link and the flag are
                # collected; the document behind it is deliberately not.
                "is_answer_key": (rprops.get("type") == "Answer Key"
                                  or rprops.get("audience") == "Verified Teacher"),
            })

        lesson_vocab = []
        for v in vocab_by_lesson.get(key, []):
            vk = (v.get("seeding_key") or {}).get("vocabulary.key")
            src = vocab.get(vk)
            if src:
                lesson_vocab.append({"word": src.get("word"),
                                     "definition": src.get("definition")})

        plan = {
            "overview_md": lprops.get("overview"),
            "student_overview_md": lprops.get("student_overview"),
            "purpose_md": lprops.get("purpose"),
            "preparation_md": lprops.get("preparation"),
            "assessment_opportunities_md": lprops.get("assessment_opportunities"),
            "objectives": objectives,
            "standards": standards,
            "opportunity_standards": opportunity,
            "vocabulary": lesson_vocab,
            "resources": lesson_resources,
            "activities": activities,
            "duration_minutes": duration or None,
            "is_assessment": bool(lprops.get("assessment")),
        }

        # The hash covers content only. Not paths, not timestamps, not the
        # commit — those change without the curriculum changing.
        digest = content_hash({
            "plan": plan,
            "levels": [{k: v for k, v in r.items() if k != "context"}
                       for r in level_records],
        })

        if has_plan and not objectives:
            warnings.append({
                "kind": "no_authored_objective",
                "script_name": script_name,
                "lesson_key": key,
                "lesson_name": name,
            })

        lessons.append({
            "stable_id": f"{script_name}::{key}",
            "script_name": script_name,
            "unit_name": unit_name,
            "lesson_key": key,
            "lesson_name": name,
            "lesson_token": lesson_token(name, row.get("relative_position") or 0),
            "slug": slugify(name),
            "relative_position": row.get("relative_position") or 0,
            "absolute_position": row.get("absolute_position") or 0,
            "has_lesson_plan": has_plan,
            "has_objectives": bool(objectives),
            "content_hash": digest,
            "plan": plan,
            "levels": level_records,
        })

    lessons.sort(key=lambda l: l["absolute_position"])
    return {
        "script_name": script_name,
        "unit_name": unit_name,
        "serialized_at": unit.get("serialized_at"),
        "published_state": unit.get("published_state"),
        "lessons": lessons,
        "warnings": warnings,
    }
