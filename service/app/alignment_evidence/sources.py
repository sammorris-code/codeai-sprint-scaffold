"""Lossless, addressable lesson evidence. Metadata is context, not performance."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()


def extract(lesson):
    plan = lesson.get("plan") or {}
    levels = lesson.get("levels") or []
    by_name = {level.get("level_name"): level for level in levels}
    alternate = "alternate" in (lesson.get("lesson_group_name") or "").lower()
    sources = []

    def add(path, text, role, context=None, level_name=None):
        if not isinstance(text, str) or not text.strip():
            return
        context = context or {}
        pathway = ("alternate" if alternate else "optional" if context.get("is_bonus")
                   else "choice" if context.get("is_choice_option") else "shared")
        sources.append({"source_id": path, "text": text, "role": role,
                        "pathway": pathway, "choice_parent": context.get("choice_parent"),
                        "level_name": level_name,
                        "is_assessment": bool(context.get("is_assessment")),
                        "text_sha256": hashlib.sha256(text.encode()).hexdigest()})

    for i, objective in enumerate(plan.get("objectives") or []):
        add(f"/plan/objectives/{i}", objective, "intended_objective")
    add("/plan/overview_md", plan.get("overview_md"), "intended_context")
    add("/plan/assessment_opportunities_md", plan.get("assessment_opportunities_md"),
        "assessment_criteria")
    for ai, activity in enumerate(plan.get("activities") or []):
        for si, section in enumerate(activity.get("sections") or []):
            path = f"/plan/activities/{ai}/sections/{si}"
            linked = [by_name[n].get("context") or {} for n in section.get("levels") or []
                      if isinstance(n, str) and n in by_name]
            # A section linked to an option must not silently become shared evidence.
            conditional = next((c for c in linked if c.get("is_choice_option")
                                or c.get("is_bonus")), {})
            add(path + "/description_md", section.get("description_md"),
                "instructional_context", conditional)
            for ti, tip in enumerate(section.get("tips") or []):
                if isinstance(tip, dict):
                    role = ("assessment_criteria" if tip.get("type") == "assessmentOpportunity"
                            else "instructional_context")
                    add(path + f"/tips/{ti}/markdown", tip.get("markdown"), role, conditional)
    for i, level in enumerate(levels):
        for field, role in (("student_text", "student_material"),
                            ("teacher_markdown", "instructional_context")):
            add(f"/levels/{i}/{field}", level.get(field), role,
                level.get("context"), level.get("level_name"))

    # Links identify resources; they are not their contents. No automatic retrieval
    # of teacher-only resources, and no assumption that a URL proves a task.
    gaps = [{"kind": "linked_resource_not_in_snapshot", "name": r.get("name"),
             "url": r.get("url"), "audience": r.get("audience")}
            for r in plan.get("resources") or [] if r.get("url")]
    if not any(s["role"] not in {"intended_objective", "intended_context"} for s in sources):
        gaps.append({"kind": "no_instructional_content"})
    record = {"stable_id": lesson["stable_id"], "lesson_name": lesson["lesson_name"],
              "content_hash": lesson.get("content_hash"), "sources": sources,
              "gaps": gaps, "alternate_progression": alternate}
    record["evidence_sha256"] = digest(record)
    return record
