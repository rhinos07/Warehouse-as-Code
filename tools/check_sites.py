#!/usr/bin/env python3
"""
Validates the site manifests under sites/ against the sibling repos.

A site manifest (schemas/site-manifest.schema.json) composes one facility
from Topology-, Allocation-, MasterData- and OrderOrchestration-as-Code.
This tool checks the composition itself, not the content of each repo
(each repo's own tools/validate.py does that):

  - the manifest matches the schema; its id matches its path
    sites/<customer>/<facility>.yaml and is unique;
  - every referenced file exists and lies under customers/<customer>/;
  - Topology and Allocation declare the same buildings for the facility;
  - every order type is reachable from the OrderOrchestration company and
    names only buildings the Topology facility has.

Then, through the manifest, the cross-repo ids (tools/cross_refs.py):
order-type targets and triggers, Allocation zones, storage points, items,
categories and owners.

Usage:
    python tools/check_sites.py                    # repos are siblings of this repo
    python tools/check_sites.py --repos-dir ../    # directory holding the repos
"""

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consistency_rules  # noqa: E402
import cross_refs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = REPO_ROOT / "schemas" / "site-manifest.schema.json"
SITES_DIR = REPO_ROOT / "sites"
REPO_NAMES = {
    "topology": "Topology-as-Code",
    "allocation": "Allocation-as-Code",
    "masterdata": "MasterData-as-Code",
    "orchestration": "OrderOrchestration-as-Code",
}


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file)


def find_repo(repos_dir: Path, name: str) -> Path | None:
    """Repo directory by name, case-insensitive (local clones are often
    lower-case, GitHub names are not)."""
    for candidate in repos_dir.iterdir() if repos_dir.is_dir() else []:
        if candidate.is_dir() and candidate.name.lower() == name.lower():
            return candidate
    return None


def relative_refs(path: Path, root_key: str, list_key: str) -> list[Path]:
    data = load_yaml(path) or {}
    return [path.parent / ref for ref in (data.get(root_key, {}) or {}).get(list_key, []) or []]


def topology_buildings(facility: Path) -> dict[str, Path]:
    """Building id (warehouse.yaml target.building) -> warehouse.yaml."""
    buildings = {}
    for warehouse in relative_refs(facility, "facility", "buildings"):
        if warehouse.exists():
            building = ((load_yaml(warehouse) or {}).get("target") or {}).get("building")
            if building:
                buildings[building] = warehouse
    return buildings


def allocation_buildings(facility: Path) -> dict[str, Path]:
    """Building id (allocation.yaml allocation.id) -> allocation.yaml."""
    buildings = {}
    for allocation in relative_refs(facility, "facility", "buildings"):
        if allocation.exists():
            building = ((load_yaml(allocation) or {}).get("allocation") or {}).get("id")
            if building:
                buildings[building] = allocation
    return buildings


def orchestration_order_types(company: Path) -> set[Path]:
    """Every order_type.yaml reachable from an OrderOrchestration company."""
    found = set()
    for channel in relative_refs(company, "company", "channels"):
        if channel.exists():
            found.update(p.resolve() for p in relative_refs(channel, "channel", "order_types"))
    return found


def check_site(path: Path, repos: dict[str, Path], seen_ids: set[str], check_ids: bool = True,
               warnings: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    data = load_yaml(path)
    validator = Draft7Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    schema_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if schema_errors:
        return [f"{path}: [{' -> '.join(map(str, e.absolute_path)) or 'root'}] {e.message}" for e in schema_errors]

    site = data["site"]
    site_id = site["id"]
    customer, facility_id = site_id.split("/")
    expected = SITES_DIR / customer / f"{facility_id}.yaml"
    if path.resolve() != expected.resolve():
        errors.append(f"{path}: site id '{site_id}' must live in sites/{customer}/{facility_id}.yaml")
    if site_id in seen_ids:
        errors.append(f"{path}: site id '{site_id}' is used by another manifest")
    seen_ids.add(site_id)

    def resolve(repo_key: str, relative: str, what: str) -> Path | None:
        if not relative.startswith(f"customers/{customer}/"):
            errors.append(f"{path}: {what} '{relative}' is not under customers/{customer}/")
        target = repos[repo_key] / relative
        if not target.exists():
            errors.append(f"{path}: {what} not found in {REPO_NAMES[repo_key]}: {relative}")
            return None
        return target

    topo_facility = resolve("topology", site["topology"]["facility"], "topology.facility")
    alloc_facility = resolve("allocation", site["allocation"]["facility"], "allocation.facility")
    resolve("masterdata", site["masterdata"]["company"], "masterdata.company")

    topo = topology_buildings(topo_facility) if topo_facility else {}
    alloc = allocation_buildings(alloc_facility) if alloc_facility else {}
    if topo_facility and alloc_facility:
        for building in sorted(topo.keys() - alloc.keys()):
            errors.append(f"{path}: building '{building}' is in Topology but has no Allocation building")
        for building in sorted(alloc.keys() - topo.keys()):
            errors.append(f"{path}: building '{building}' is in Allocation but not in Topology")

    company = repos["orchestration"] / "customers" / customer / "company.yaml"
    reachable = orchestration_order_types(company) if company.exists() else set()
    if not company.exists():
        errors.append(f"{path}: OrderOrchestration company not found: customers/{customer}/company.yaml")
    listed: set[Path] = set()
    for i, entry in enumerate(site["order_types"]):
        order_type = resolve("orchestration", entry["path"], f"order_types[{i}].path")
        if order_type is None:
            continue
        for j, example_dir in enumerate(entry.get("examples", [])):
            # Examples live outside customers/, so only existence is checked.
            if not (repos["orchestration"] / example_dir).is_dir():
                errors.append(f"{path}: order_types[{i}].examples[{j}] not found in OrderOrchestration-as-Code: {example_dir}")
        if order_type.resolve() in listed:
            errors.append(f"{path}: order_types[{i}] lists '{entry['path']}' twice")
        listed.add(order_type.resolve())
        if company.exists() and order_type.resolve() not in reachable:
            errors.append(f"{path}: order_types[{i}] '{entry['path']}' is not listed by any channel of the company")
        if topo_facility:
            for building in entry["buildings"]:
                if building not in topo:
                    errors.append(f"{path}: order_types[{i}] names building '{building}', not in the Topology facility")
    if errors or not check_ids:
        return errors  # ids are only meaningful once the composition holds

    compiled = {}
    entities_by_building = {}
    for building, warehouse in topo.items():
        try:
            entities_by_building[building] = cross_refs.compile_building_entities(repos["topology"], warehouse)
        except RuntimeError as error:
            errors.append(f"{path}: {error}")
            continue
        compiled[building] = {
            kind: {item["id"] for item in items} for kind, items in entities_by_building[building].items()
        }
    if errors:
        return errors
    known_process_types = cross_refs.process_types(repos["topology"])
    md = cross_refs.masterdata_ids(repos["masterdata"] / site["masterdata"]["company"])
    for entry in site["order_types"]:
        order_type_file = repos["orchestration"] / entry["path"]
        errors += cross_refs.check_order_type(
            order_type_file, entry["buildings"], compiled, known_process_types
        )
        order_type_id = ((cross_refs.load_yaml(order_type_file) or {}).get("order_type") or {}).get("id")
        for example_dir in entry.get("examples", []):
            errors += cross_refs.check_examples(
                repos["orchestration"] / example_dir, order_type_id, entry["buildings"], compiled, md
            )
    for building, allocation in alloc.items():
        errors += cross_refs.check_allocation_building(allocation, compiled.get(building, {}), md)
    if errors:
        return errors  # consistency rules assume the ids resolve

    # Consistency rules (backlog C1a): R11, R4, R5.
    try:
        items = consistency_rules.compiled_items(repos["masterdata"], repos["masterdata"] / site["masterdata"]["company"])
    except RuntimeError as error:
        return errors + [f"{path}: {error}"]
    catalog = cross_refs.load_yaml(repos["masterdata"] / "elements" / "load_unit_types.yaml") or {}
    load_unit_types = {lu["id"] for lu in catalog.get("load_unit_types", [])}
    select_rule = consistency_rules.load_precedence(repos["allocation"])
    for building, allocation in alloc.items():
        for level, message in consistency_rules.check_putaway_rules(
            allocation, entities_by_building.get(building, {}), items, load_unit_types, select_rule
        ):
            if level == "error":
                errors.append(message)
            elif warnings is not None:
                warnings.append(message)
    return errors


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repos-dir", type=Path, default=REPO_ROOT.parent,
                        help="Directory holding the sibling repos (default: parent of this repo).")
    args = parser.parse_args(argv[1:])

    repos: dict[str, Path] = {}
    for key, name in REPO_NAMES.items():
        found = find_repo(args.repos_dir.resolve(), name)
        if found is None:
            print(f"❌ {name} not found in {args.repos_dir}")
            return 2
        repos[key] = found

    manifests = sorted(SITES_DIR.glob("*/*.yaml"))
    if not manifests:
        print(f"No site manifests in {SITES_DIR}")
        return 2
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for manifest in manifests:
        errors += check_site(manifest, repos, seen, warnings=warnings)
    if warnings:
        print(f"⚠ {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"  - {warning}")
    if errors:
        print(f"❌ {len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"✅ {len(manifests)} site manifest(s) consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
