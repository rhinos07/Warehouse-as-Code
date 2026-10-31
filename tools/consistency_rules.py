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
  R1   FEFO or a shelf-life floor in the search rule of an item without
       tracked expiry (error for a rule scoped to the item, its category
       or owner; warning for the default rule, which also serves others)
  R2   search shelf-life floor above the item's total shelf life (error:
       no stock can ever qualify) or above its receipt minimum (warning:
       stock accepted at receipt may never ship)
  R3   allow_mixed_lots on putaway steps of a rule that only serves items
       without lot tracking (warning: no effect)
  R8   fixed bin whose place does not accept the load unit of the item's
       packaging level in that uom (error)
  R9   fixed bin uom that the item's packaging does not define (error)
  R6   putaway rule scoped to one item with a step into a zone reserved
       for other owners (error: that step can never be used)
  R10  fixed place in a zone reserved for other owners (error)
  R12  shortage policy allows substitution, but no item has a substitute
       (warning), or a substitute id is unknown (error)
  R7 (owner unknown to the company) is covered by the id checks in
       cross_refs.py.
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


def strategy_file(allocation: Path, name: str) -> tuple[Path | None, dict]:
    imports = (load_yaml(allocation) or {}).get("allocation", {}).get("imports", []) or []
    for ref in imports:
        path = allocation.parent / ref
        if path.name == name and path.exists():
            return path, load_yaml(path) or {}
    return None, {}


def packaging_by_item(company: Path) -> dict[str, dict[str, dict]]:
    """item id -> uom -> packaging level, from each category's packaging.yaml."""
    data = (load_yaml(company) or {}).get("company", {}) or {}
    result: dict[str, dict[str, dict]] = {}
    for ref in data.get("categories", []) or []:
        category_file = company.parent / ref
        category = (load_yaml(category_file) or {}).get("category", {}) or {}
        for imported in category.get("imports", []) or []:
            path = category_file.parent / imported
            if path.name != "packaging.yaml" or not path.exists():
                continue
            for entry in (load_yaml(path) or {}).get("packaging", []) or []:
                result[entry.get("item_id")] = {
                    level.get("uom"): level for level in entry.get("uom_hierarchy", []) or []
                }
    return result


def check_search_rules(allocation: Path, items: list[dict], select_rule) -> list[tuple[str, str]]:
    """R1 and R2 for one building."""
    findings: list[tuple[str, str]] = []
    path, data = strategy_file(allocation, "search_rules.yaml")
    rules = data.get("search_rules", []) or []
    if path is None:
        return findings
    for item in items:
        rule = select_rule(rules, item)
        if rule is None:
            continue
        expiry = (item.get("tracking") or {}).get("expiry") or {}
        tracked = bool(expiry.get("tracked"))
        scoped = bool(rule.get("applies_to"))
        uses_fefo = any(step.get("selection_strategy") == "FEFO" for step in rule.get("steps", []))
        floors = [
            (step.get("constraints") or {}).get("min_remaining_shelf_life_days")
            for step in rule.get("steps", [])
        ]
        floors = [f for f in floors if isinstance(f, (int, float))]
        where = f"{path.name} search_rule '{rule.get('id')}'"
        if not tracked and (uses_fefo or floors):
            what = "FEFO" if uses_fefo else "a shelf-life floor"
            findings.append((
                "error" if scoped else "warning",
                f"{where}: R1 uses {what} for item '{item.get('id')}', which has no tracked expiry",
            ))
            continue
        if tracked and floors:
            floor = max(floors)
            total = expiry.get("total_shelf_life_days")
            receipt = expiry.get("min_remaining_at_receipt_days")
            if isinstance(total, (int, float)) and floor > total:
                findings.append(("error", f"{where}: R2 shelf-life floor {floor} days exceeds item '{item.get('id')}' total shelf life {total} days; no stock can qualify"))
            elif isinstance(receipt, (int, float)) and floor > receipt:
                findings.append(("warning", f"{where}: R2 shelf-life floor {floor} days is above item '{item.get('id')}' receipt minimum {receipt} days; accepted stock may never ship"))
    return [(level, f"{allocation}: {message}") for level, message in findings]


def check_mixed_lots(allocation: Path, items: list[dict], select_rule) -> list[tuple[str, str]]:
    """R3 for one building."""
    path, rules = putaway_rules(allocation)
    if path is None:
        return []
    served: dict[str, list[dict]] = {}
    for item in items:
        rule = select_rule(rules, item)
        if rule is not None:
            served.setdefault(rule.get("id"), []).append(item)
    findings = []
    for rule in rules:
        sets_lots = any("allow_mixed_lots" in (step.get("constraints") or {}) for step in rule.get("steps", []))
        members = served.get(rule.get("id"), [])
        if sets_lots and members and all((m.get("tracking") or {}).get("lot") == "none" for m in members):
            findings.append(("warning", f"{allocation}: {path.name} putaway_rule '{rule.get('id')}': R3 allow_mixed_lots has no effect, every item it serves has lot tracking 'none'"))
    return findings


def check_fixed_bins(allocation: Path, entities: dict[str, list[dict]], items: list[dict],
                     packaging: dict[str, dict[str, dict]]) -> list[tuple[str, str]]:
    """R8 and R9 for one building."""
    path, data = strategy_file(allocation, "fixed_bin_assignments.yaml")
    if path is None:
        return []
    points = {p["id"]: p for p in entities.get("storage_point", [])}
    by_id = {item.get("id"): item for item in items}
    findings = []
    for index, entry in enumerate(data.get("fixed_bin_assignments", []) or []):
        item = by_id.get(entry.get("item_id"))
        if item is None:
            continue  # unknown item: reported by the id checks
        uom = entry.get("uom") or item.get("default_uom")
        levels = packaging.get(item.get("id"), {})
        where = f"{path.name} fixed_bin_assignments[{index}] ({item.get('id')} @ {entry.get('storage_point')})"
        if levels and uom not in levels:
            findings.append(("error", f"{where}: R9 uom '{uom}' is not a packaging level of the item ({', '.join(levels)})"))
            continue
        load_unit = (levels.get(uom) or {}).get("load_unit_type")
        allowed = (points.get(entry.get("storage_point")) or {}).get("allowed_load_unit_types") or []
        if load_unit and allowed and load_unit not in allowed:
            findings.append(("error", f"{where}: R8 the item is stored as '{load_unit}' in uom '{uom}', the place accepts only {', '.join(allowed)}"))
    return [(level, f"{allocation}: {message}") for level, message in findings]


def reserved_zones(allocation: Path) -> dict[tuple[str, str], set[str]]:
    """(zone type, zone id) -> owners allowed, from structure/owner_zones.yaml."""
    _, data = strategy_file(allocation, "owner_zones.yaml")
    reserved: dict[tuple[str, str], set[str]] = {}
    for entry in data.get("owner_zones", []) or []:
        zone = entry.get("zone") or {}
        reserved.setdefault((zone.get("type"), zone.get("id")), set()).update(entry.get("owners", []) or [])
    return reserved


def point_zones(point: dict, entities: dict[str, list[dict]]) -> set[tuple[str, str]]:
    """Zones a storage point belongs to: its storage type and every
    activity area that draws bins from its storage type or section."""
    zones = {("storage_type", point.get("storage_type"))}
    for area in entities.get("activity_area", []):
        sources = set(area.get("bins_from", []))
        if point.get("storage_type") in sources or point.get("section") in sources:
            zones.add(("activity_area", area["id"]))
    return zones


def check_owner_rules(allocation: Path, entities: dict[str, list[dict]], items: list[dict]) -> list[tuple[str, str]]:
    """R6 and R10 for one building."""
    reserved = reserved_zones(allocation)
    if not reserved:
        return []
    by_id = {item.get("id"): item for item in items}
    findings = []

    path, rules = putaway_rules(allocation)
    for rule in rules or []:
        item = by_id.get((rule.get("applies_to") or {}).get("item_id"))
        if item is None:
            continue  # owner and category scopes are checked by Allocation itself
        for index, step in enumerate(rule.get("steps", [])):
            zone = step.get("zone") or {}
            owners = reserved.get((zone.get("type"), zone.get("id")))
            if owners is not None and item.get("owner") not in owners:
                findings.append(("error", f"{path.name} putaway_rule '{rule.get('id')}' steps[{index}]: R6 {zone.get('type')} '{zone.get('id')}' is reserved for {', '.join(sorted(owners))}, item '{item.get('id')}' belongs to '{item.get('owner')}'"))

    fixed_path, data = strategy_file(allocation, "fixed_bin_assignments.yaml")
    points = {p["id"]: p for p in entities.get("storage_point", [])}
    for index, entry in enumerate(data.get("fixed_bin_assignments", []) or []):
        item = by_id.get(entry.get("item_id"))
        point = points.get(entry.get("storage_point"))
        if item is None or point is None:
            continue
        for zone in sorted(point_zones(point, entities)):
            owners = reserved.get(zone)
            if owners is not None and item.get("owner") not in owners:
                findings.append(("error", f"{fixed_path.name} fixed_bin_assignments[{index}]: R10 place '{point['id']}' lies in {zone[0]} '{zone[1]}', reserved for {', '.join(sorted(owners))}; item '{item.get('id')}' belongs to '{item.get('owner')}'"))
    return [(level, f"{allocation}: {message}") for level, message in findings]


def substitutes(company: Path) -> dict[str, str]:
    """item id -> substitute_item_id, from each category's lifecycle.yaml."""
    data = (load_yaml(company) or {}).get("company", {}) or {}
    result: dict[str, str] = {}
    for ref in data.get("categories", []) or []:
        category_file = company.parent / ref
        category = (load_yaml(category_file) or {}).get("category", {}) or {}
        for imported in category.get("imports", []) or []:
            path = category_file.parent / imported
            if path.name != "lifecycle.yaml" or not path.exists():
                continue
            for entry in (load_yaml(path) or {}).get("lifecycle", []) or []:
                if entry.get("substitute_item_id"):
                    result[entry.get("item_id")] = entry["substitute_item_id"]
    return result


def check_substitution(order_type: Path, company: Path, items: list[dict]) -> list[tuple[str, str]]:
    """R12 for one order type."""
    imports = (load_yaml(order_type) or {}).get("order_type", {}).get("imports", []) or []
    policy_file = next((order_type.parent / ref for ref in imports if ref.endswith("shortage_policy.yaml")), None)
    if policy_file is None or not policy_file.exists():
        return []
    policy = (load_yaml(policy_file) or {}).get("shortage_policy", {}) or {}
    if not policy.get("allow_substitution"):
        return []
    known = {item.get("id") for item in items}
    subs = substitutes(company)
    if not subs:
        return [("warning", f"{policy_file}: R12 allow_substitution is true, but no item of the company has a substitute_item_id")]
    return [
        ("error", f"{policy_file}: R12 item '{item_id}' names substitute '{sub}', which is not an item of the company")
        for item_id, sub in sorted(subs.items()) if sub not in known
    ]
