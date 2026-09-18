"""Reusable cached stages. Cache model answers, revalidate on every use."""
import json
from pathlib import Path

from ..alignment_evidence import judge
from ..alignment_evidence.sources import digest
from . import inventory, performances, alignment, rollup

VERSION = "lesson-unit-course-v2"


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


class Calls:
    def __init__(self, client, model, cache, live=False, checkpoint=None, max_failures=3):
        self.client, self.model, self.cache, self.live = client, model, Path(cache), live
        self.checkpoint, self.max_failures = checkpoint, max_failures
        self.usage, self.log, self.failures = {}, [], {}

    def ask(self, stage, rules, prefix, payload, schema, validator):
        key = digest({"stage": stage, "rules": rules, "prefix": prefix, "payload": payload,
                      "schema": schema, "model": self.model, "protocol": VERSION})
        path = self.cache / (key + ".json")
        cached = path.exists()
        if not cached and (not self.live or len(self.failures) >= self.max_failures):
            raise LookupError(f"Stage {stage} has no cached response")
        try:
            if cached:
                entry = json.loads(path.read_text(encoding="utf-8"))
                if entry["key"] != key or digest(entry["answer"]) != entry["answer_sha256"]:
                    raise ValueError("Cache fingerprint mismatch")
                answer = entry["answer"]
            else:
                answer = judge.call(self.client, self.model, rules, prefix, payload, schema, self.usage)
            result = validator(answer)
            if not cached:
                write(path, {"key": key, "answer": answer, "answer_sha256": digest(answer), "model": self.model})
            self.log.append({"stage": stage, "cache_key": key, "cached": cached})
            return result
        except Exception as exc:
            self.failures[stage + ":" + key] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if self.checkpoint:
                write(self.checkpoint, {"usage": self.usage, "stages": self.log, "failures": self.failures})


def run(evidence, standards, routes, calls, selected_ids=None, supplied_specs=None, stage="all", save=None):
    selected = set(selected_ids or [e["stable_id"] for e in evidence])
    inventories, summaries, lesson_results, unit_results, failures = {}, {}, {}, {}, {}
    specs = supplied_specs
    if specs is not None:
        performances.validate(specs, standards)
    discovery = {}

    def snapshot():
        state = {"inventories": inventories, "unit_summaries": summaries, "specs": specs,
                 "discovery": discovery, "lesson_results": lesson_results,
                 "unit_results": unit_results, "failures": failures}
        if save:
            save(state)
        return state

    def attempt(label, operation):
        try:
            return operation()
        except Exception as exc:
            failures[label] = f"{type(exc).__name__}: {exc}"
            return None

    if stage != "performances":
        for e in evidence:
            if e["stable_id"] not in selected:
                continue
            inv = attempt("inventory:" + e["stable_id"], lambda: calls.ask(
                "inventory", inventory.RULES, "Framework-independent instructional evidence.", e,
                inventory.SCHEMA, lambda a: inventory.validate(a, e)))
            if inv is not None:
                inventories[e["stable_id"]] = inv
            snapshot()
        for key in dict.fromkeys(e["unit_key"] for e in evidence):
            members = [i for i in inventories.values() if i["unit_key"] == key]
            if not members:
                continue
            summary = attempt("unit-summary:" + key, lambda: calls.ask(
                "unit_summary", inventory.UNIT_RULES, "Framework-independent unit sequence.", members,
                inventory.UNIT_SCHEMA, lambda a: inventory.validate_unit(a, members)))
            if summary is not None:
                summaries[key] = summary
            snapshot()

    if stage != "inventory" and specs is None:
        specs = []
        for start in range(0, len(standards), 10):
            batch = standards[start:start + 10]
            drafted = attempt(f"performances:{start}", lambda: calls.ask(
                "performances", performances.RULES, "Original state requirements only.",
                [{"standard_id": s["identifier"], "statement": s["statement"]} for s in batch],
                performances.SCHEMA, lambda a: performances.validate(a["standards"], batch)))
            if drafted is None:
                specs = None  # an incomplete requirement set must never shrink the denominator
                break
            specs.extend(drafted)
            snapshot()
    if specs is not None:
        performances.validate(specs, standards)
    if stage != "all" or specs is None:
        return snapshot()

    for lid, inv in inventories.items():
        def nominate(a):
            candidates = a["candidates"]
            ids = [c["standard_id"] for c in candidates]
            if len(ids) != len(set(ids)) or set(ids) - {s["standard_id"] for s in specs}:
                raise ValueError("Discovery returned duplicate/invented standards")
            return candidates
        candidates = attempt("discovery:" + lid, lambda: calls.ask(
            "discovery", alignment.DISCOVERY_RULES, specs, inv,
            alignment.DISCOVERY_SCHEMA, nominate))
        if candidates is None:
            continue
        discovery[lid] = candidates
        nominated = {c["standard_id"] for c in candidates}
        chosen = [s for s in specs if s["standard_id"] in nominated]
        qualified = []
        for start in range(0, len(chosen), 10):
            batch = chosen[start:start + 10]
            result = attempt(f"lesson:{lid}:{start}", lambda: calls.ask(
                "lesson_qualification", alignment.RULES, batch, inv, alignment.SCHEMA,
                lambda a: alignment.qualify(a, batch, inv["items"], "lesson")))
            if result is not None:
                for verdict in result:
                    verdict["unit_key"] = inv["unit_key"]
                qualified.extend(result)
        lesson_results[lid] = qualified
        snapshot()
    # Recall safeguard: no candidate standard is excluded from the unit pass.
    for key in dict.fromkeys(e["unit_key"] for e in evidence):
        members = [i for i in inventories.values() if i["unit_key"] == key]
        if not members:
            continue
        items = [item for member in members for item in member["items"]]
        payload = {"lessons": members, "sequence": summaries.get(key),
                   "scope": "Available lessons only; missing lessons remain unknown."}
        unit_results[key] = []
        for start in range(0, len(specs), 10):
            batch = specs[start:start + 10]
            result = attempt(f"unit:{key}:{start}", lambda: calls.ask(
                "unit_qualification", alignment.UNIT_RULES, batch, payload, alignment.SCHEMA,
                lambda a: alignment.qualify(a, batch, items, "unit")))
            if result is not None:
                for verdict in result:
                    verdict["unit_key"] = key
                unit_results[key].extend(result)
            snapshot()
    state = snapshot()
    state["coverage"] = rollup.build(specs, evidence, inventories, lesson_results, unit_results, routes["domains"])
    return state
