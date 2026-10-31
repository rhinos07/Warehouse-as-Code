"""Cross-repo id checks for one site (backlog C1, first rules).

Resolves the references one repo makes into another, through the site
manifest:

  - OrderOrchestration targets (door / work_center / activity_area in
    split, completion and other rules) exist in a building the order
    type serves;
  - OrderOrchestration workflow triggers name a Topology process_type;
  - Allocation zones (storage_type / activity_area) and storage points
    exist in the Topology building with the same id;
  - item ids, categories and owners used by Allocation exist in the
    site's MasterData company.

Topology buildings are compiled with Topology-as-Code's own
tools/compile.py, so the check sees the same ids a WMS import would.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

TARGET_TYPES = {"door", "work_center", "activity_area"}
ZONE_TYPES = {"storage_type", "activity_area"}


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


def imported_files(root_file: Path, root_key: str) -> list[Path]:
    data = load_yaml(root_file) or {}
    imports = (data.get(root_key) or {}).get("imports", []) or []
    return [root_file.parent / ref for ref in imports if (root_file.parent / ref).exists()]


def compile_building(topology_repo: Path, warehouse: Path) -> dict[str, set[str]]:
    """entity type -> ids of one compiled Topology building."""
    entities = compile_building_entities(topology_repo, warehouse)
    return {kind: {item["id"] for item in items} for kind, items in entities.items()}


def compile_building_entities(topology_repo: Path, warehouse: Path) -> dict[str, list[dict]]:
    """entity type -> compiled entities of one Topology building."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "artifact.yaml"
        result = subprocess.run(
            [sys.executable, str(topology_repo / "tools" / "compile.py"), str(warehouse), "--output", str(out)],
            cwd=topology_repo, capture_output=True, text=True,
        )
        if result.returncode != 0 or not out.exists():
            raise RuntimeError(f"Topology compile failed for {warehouse}:\n{result.stdout}{result.stderr}")
        return (load_yaml(out) or {}).get("entities", {})


def process_types(topology_repo: Path) -> set[str]:
    catalog = load_yaml(topology_repo / "elements" / "process_types.yaml") or {}
    return {item["id"] for item in catalog.get("process_types", [])}


def masterdata_ids(company: Path) -> dict[str, set[str]]:
    """items, categories and owners of a MasterData company."""
    data = (load_yaml(company) or {}).get("company", {}) or {}
    ids = {
        "item": set(),
        "category": set(),
        "owner": {owner.get("id") for owner in data.get("owners", []) or []},
    }
    for ref in data.get("categories", []) or []:
        category_file = company.parent / ref
        if not category_file.exists():
            continue
        category = (load_yaml(category_file) or {}).get("category", {}) or {}
        ids["category"].add(category.get("id"))
        for imported in imported_files(category_file, "category"):
            for item in (load_yaml(imported) or {}).get("items", []) or []:
                ids["item"].add(item.get("id"))
    return ids


def walk(node, path=()):
    """Yields (path, dict) for every dict in a YAML tree."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from walk(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, path + (index,))


def where(path) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")


def check_order_type(order_type: Path, buildings: list[str], compiled: dict[str, dict[str, set[str]]],
                     known_process_types: set[str]) -> list[str]:
    errors = []
    targets: dict[str, set[str]] = {kind: set() for kind in TARGET_TYPES}
    for building in buildings:
        for kind in TARGET_TYPES:
            targets[kind] |= compiled.get(building, {}).get(kind, set())
    for imported in imported_files(order_type, "order_type"):
        for path, node in walk(load_yaml(imported) or {}):
            if set(node) == {"type", "id"} and node["type"] in TARGET_TYPES:
                if node["id"] not in targets[node["type"]]:
                    errors.append(
                        f"{imported.name} {where(path)}: {node['type']} '{node['id']}'"
                        f" not found in building(s) {', '.join(buildings)}"
                    )
            if imported.name == "workflow_triggers.yaml" and "trigger" in node and isinstance(node["trigger"], str):
                if node["trigger"] not in known_process_types:
                    errors.append(f"{imported.name} {where(path)}: trigger '{node['trigger']}' is not a Topology process_type")
    return [f"{order_type}: {error}" for error in errors]


def check_allocation_building(allocation: Path, ids: dict[str, set[str]], md: dict[str, set[str]]) -> list[str]:
    errors = []
    for imported in imported_files(allocation, "allocation"):
        for path, node in walk(load_yaml(imported) or {}):
            if set(node) == {"type", "id"} and node["type"] in ZONE_TYPES:
                if node["id"] not in ids.get(node["type"], set()):
                    errors.append(f"{imported.name} {where(path)}: {node['type']} '{node['id']}' not in the Topology building")
            point = node.get("storage_point")
            if isinstance(point, str) and point not in ids.get("storage_point", set()):
                errors.append(f"{imported.name} {where(path)}: storage_point '{point}' not in the Topology building")
            for key, kind in (("item_id", "item"), ("category", "category"), ("owner", "owner")):
                value = node.get(key)
                if isinstance(value, str) and value not in md[kind]:
                    errors.append(f"{imported.name} {where(path)}: {kind} '{value}' not in MasterData")
    return [f"{allocation}: {error}" for error in errors]


def check_examples(directory: Path, order_type_id: str, buildings: list[str],
                   compiled: dict[str, dict[str, set[str]]], md: dict[str, set[str]]) -> list[str]:
    """Illustrative order instances: every example in the directory that
    belongs to this order type has header targets in the served buildings
    and position item ids in MasterData."""
    errors = []
    targets: dict[str, set[str]] = {kind: set() for kind in TARGET_TYPES}
    for building in buildings:
        for kind in TARGET_TYPES:
            targets[kind] |= compiled.get(building, {}).get(kind, set())
    for example in sorted(directory.glob("*.yaml")):
        data = load_yaml(example) or {}
        order = data.get("order") or {}
        if order.get("order_type") != order_type_id:
            continue
        for path, node in walk(data):
            if set(node) == {"type", "id"} and node["type"] in TARGET_TYPES:
                if node["id"] not in targets[node["type"]]:
                    errors.append(f"{example.name} {where(path)}: {node['type']} '{node['id']}' not found in building(s) {', '.join(buildings)}")
            item = node.get("item_id")
            if isinstance(item, str) and item not in md["item"]:
                errors.append(f"{example.name} {where(path)}: item '{item}' not in MasterData")
    return [f"{directory}: {error}" for error in errors]
