"""Cross-repo consistency rules (Warehouse-as-Code backlog C1a).

The runtime enforces these rules on every task (it never puts a chilled
item into an ambient place, it checks the load unit at the place). These
checks do not repeat that. They find configuration the runtime can never
satisfy, or settings the runtime will always override:

  - error:   a rule can never work as configured;
  - warning: a setting has no effect.

Implemented here:
  R11  putaway rule vs. item storage condition (error if no step of the
       item's putaway rule has a place with the item's condition)
  R4   putaway step load_unit_types vs. load unit catalog and the zone's
       allowed_load_unit_types (error for an unknown id or a type no place
       in the zone accepts)
  R5   allow_mixed_items: true on a zone whose places all require
       homogeneity (warning: the runtime keeps them homogeneous anyway)
"""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_precedence(allocation_repo: Path):
    """Allocation-as-Code's own select_rule, so the rule chosen per item is
    the same one a runtime would choose."""
    spec = importlib.util.spec_from_file_location(
        "allocation_precedence", allocation_repo / "tools" / "precedence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.select_rule


def compiled_items(masterdata_repo: Path, company: Path) -> list[dict]:
    """Items of a MasterData company, resolved by MasterData-as-Code's own
    compile.py (category inheritance of storage_condition, owner, tracking)."""
    data = (load_yaml(company) or {}).get("company", {}) or {}
    items: list[dict] = []
    for ref in data.get("categories", []) or []:
        category = company.parent / ref
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "items.yaml"
            result = subprocess.run(
                [sys.executable, str(masterdata_repo / "tools" / "compile.py"), str(category), "--output", str(out)],
                cwd=masterdata_repo, capture_output=True, text=True,
            )
            if result.returncode != 0 or not out.exists():
                raise RuntimeError(f"MasterData compile failed for {category}:\n{result.stdout}{result.stderr}")
            items += (load_yaml(out) or {}).get("items", []) or []
    return items


def zone_points(zone: dict, entities: dict[str, list[dict]]) -> list[dict]:
    """Compiled storage points that belong to a zone (storage_type, or an
    activity_area through its bins_from storage types / sections)."""
    points = entities.get("storage_point", [])
    if zone.get("type") == "storage_type":
        return [p for p in points if p.get("storage_type") == zone.get("id")]
    if zone.get("type") == "activity_area":
        area = next((a for a in entities.get("activity_area", []) if a["id"] == zone.get("id")), None)
        sources = set((area or {}).get("bins_from", []))
        return [p for p in points if p.get("storage_type") in sources or p.get("section") in sources]
    return []


def putaway_rules(allocation: Path) -> tuple[Path | None, list[dict]]:
    imports = (load_yaml(allocation) or {}).get("allocation", {}).get("imports", []) or []
    for ref in imports:
        path = allocation.parent / ref
        if path.name == "putaway_rules.yaml" and path.exists():
            return path, (load_yaml(path) or {}).get("putaway_rules", []) or []
    return None, []


def check_putaway_rules(allocation: Path, entities: dict[str, list[dict]], items: list[dict],
                        load_unit_types: set[str], select_rule) -> list[tuple[str, str]]:
    """R11, R4, R5 for one building. Returns (level, message) pairs."""
    findings: list[tuple[str, str]] = []
    path, rules = putaway_rules(allocation)
    if path is None:
        return findings
    storage_types = {st["id"]: st for st in entities.get("storage_type", [])}

    # R4 and R5: per step, independent of items.
    for rule in rules:
        for index, step in enumerate(rule.get("steps", [])):
            where = f"{path.name} putaway_rule '{rule.get('id')}' steps[{index}]"
            zone = step.get("zone") or {}
            points = zone_points(zone, entities)
            constraints = step.get("constraints") or {}
            allowed = {lu for p in points for lu in p.get("allowed_load_unit_types", []) or []}
            for lu in constraints.get("load_unit_types", []) or []:
                if lu not in load_unit_types:
                    findings.append(("error", f"{where}: R4 load unit type '{lu}' is not in the load unit catalog"))
                elif points and allowed and lu not in allowed:
                    findings.append(("error", f"{where}: R4 no place in {zone.get('type')} '{zone.get('id')}' accepts load unit type '{lu}'"))
            if constraints.get("allow_mixed_items") is True and points and all(
                storage_types.get(p.get("storage_type"), {}).get("homogeneity_required") for p in points
            ):
                findings.append(("warning", f"{where}: R5 allow_mixed_items has no effect, every place in {zone.get('type')} '{zone.get('id')}' requires homogeneity"))

    # R11: per item, against the putaway rule a runtime would choose for it.
    for item in items:
        condition = item.get("storage_condition")
        if not condition:
            continue
        rule = select_rule(rules, item)
        if rule is None:
            continue
        conditions_seen: set[str] = set()
        possible = False
        for step in rule.get("steps", []):
            for point in zone_points(step.get("zone") or {}, entities):
                point_condition = point.get("storage_condition")
                if point_condition is None or point_condition == condition:
                    possible = True  # unknown condition: cannot prove it impossible
                    break
                conditions_seen.add(point_condition)
            if possible:
                break
        if not possible and conditions_seen:
            findings.append((
                "error",
                f"{path.name} putaway_rule '{rule.get('id')}': R11 item '{item.get('id')}' needs "
                f"'{condition}', but no step zone has such a place (only {', '.join(sorted(conditions_seen))})",
            ))
    return [(level, f"{allocation}: {message}") for level, message in findings]
