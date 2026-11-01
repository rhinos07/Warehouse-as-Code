"""Tests for tools/cross_refs.py - cross-repo id checks. Uses small
in-memory id sets and temp files instead of compiled Topology artifacts."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import cross_refs  # noqa: E402


def write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


class CrossRefsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.compiled = {"h1": {
            "door": {"DOOR_01"}, "work_center": {"EXIT"}, "activity_area": {"PICK_A"},
            "storage_type": {"HBR"}, "storage_point": {"HBR.01-01-01"},
        }}

    def order_type(self, split_rules, triggers=None):
        root = self.tmp / "ot"
        write(root / "strategies/split_rules.yaml", {"split_rules": split_rules})
        imports = ["strategies/split_rules.yaml"]
        if triggers is not None:
            write(root / "strategies/workflow_triggers.yaml", {"workflow_triggers": triggers})
            imports.append("strategies/workflow_triggers.yaml")
        return write(root / "order_type.yaml", {"order_type": {"id": "ot", "imports": imports}})

    def test_known_target_passes(self):
        ot = self.order_type([{"id": "S1", "target_override": {"type": "work_center", "id": "EXIT"}}])
        self.assertEqual(cross_refs.check_order_type(ot, ["h1"], self.compiled, {"pick_task"}), [])

    def test_unknown_target_is_reported(self):
        ot = self.order_type([{"id": "S1", "target_override": {"type": "activity_area", "id": "NOWHERE"}}])
        errors = cross_refs.check_order_type(ot, ["h1"], self.compiled, set())
        self.assertTrue(any("'NOWHERE'" in e and "h1" in e for e in errors), errors)

    def test_unknown_trigger_is_reported(self):
        ot = self.order_type([], [{"id": "S1", "trigger": "teleport_task"}])
        errors = cross_refs.check_order_type(ot, ["h1"], self.compiled, {"pick_task"})
        self.assertTrue(any("teleport_task" in e for e in errors), errors)

    def test_allocation_refs(self):
        root = self.tmp / "alloc"
        write(root / "strategies/rules.yaml", {"search_rules": [
            {"id": "R1", "applies_to": {"item_id": "ITEM_X"},
             "steps": [{"zone": {"type": "storage_type", "id": "BLK"}}]},
        ], "fixed_bin_assignments": [{"item_id": "ITEM_1", "storage_point": "HBR.09-09-09"}]})
        allocation = write(root / "allocation.yaml", {"allocation": {"id": "h1", "imports": ["strategies/rules.yaml"]}})
        md = {"item": {"ITEM_1"}, "category": set(), "owner": set()}
        errors = cross_refs.check_allocation_building(allocation, self.compiled["h1"], md)
        self.assertTrue(any("item 'ITEM_X'" in e for e in errors), errors)
        self.assertTrue(any("storage_type 'BLK'" in e for e in errors), errors)
        self.assertTrue(any("storage_point 'HBR.09-09-09'" in e for e in errors), errors)
        self.assertFalse(any("ITEM_1'" in e for e in errors), errors)

    def test_masterdata_ids(self):
        company = self.tmp / "md/company.yaml"
        write(company, {"company": {"id": "c", "owners": [{"id": "O1"}], "categories": ["categories/a/category.yaml"]}})
        write(self.tmp / "md/categories/a/category.yaml", {"category": {"id": "a", "imports": ["structure/items.yaml"]}})
        write(self.tmp / "md/categories/a/structure/items.yaml", {"items": [{"id": "I1"}]})
        ids = cross_refs.masterdata_ids(company)
        self.assertEqual(ids, {"item": {"I1"}, "category": {"a"}, "owner": {"O1"}})


    def test_examples_targets_and_items(self):
        examples = self.tmp / "examples/walk"
        write(examples / "01.yaml", {
            "order": {"order_id": "O1", "order_type": "ot",
                      "target": {"type": "door", "id": "DOOR_01"},
                      "order_target": {"type": "door", "id": "GATE_9"}},
            "positions": [{"line_id": "L1", "material_request": {"item_id": "I9", "quantity": 1, "uom": "each"}}],
        })
        write(examples / "02.yaml", {"order": {"order_id": "O2", "order_type": "other",
                                               "target": {"type": "door", "id": "NOPE"}}})
        md = {"item": {"I1"}, "category": set(), "owner": set()}
        errors = cross_refs.check_examples(examples, "ot", ["h1"], self.compiled, md)
        self.assertTrue(any("'GATE_9'" in e for e in errors), errors)
        self.assertTrue(any("item 'I9'" in e for e in errors), errors)
        self.assertFalse(any("NOPE" in e for e in errors), "other order types are skipped")
        self.assertFalse(any("DOOR_01" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()


class LoadUnitIdsTest(unittest.TestCase):
    """Site-level carrier check: global MasterData catalog + the company's
    customers/<c>/load_unit_types.yaml."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        write(self.tmp / "md/elements/load_unit_types.yaml", {"load_unit_types": [{"id": "pallet_euro"}]})
        self.company = write(self.tmp / "md/customers/acme/company.yaml", {"company": {"id": "acme"}})

    def test_global_only(self):
        self.assertEqual(cross_refs.load_unit_ids(self.tmp / "md", self.company), {"pallet_euro"})

    def test_customer_catalog_extends_global(self):
        write(self.company.parent / "load_unit_types.yaml", {"load_unit_types": [{"id": "acme_crate"}]})
        self.assertEqual(cross_refs.load_unit_ids(self.tmp / "md", self.company), {"pallet_euro", "acme_crate"})

    def test_unknown_topology_carrier_is_error(self):
        entities = {
            "storage_point": [
                {"id": "A.01", "allowed_load_unit_types": ["pallet_euro", "ghost"]},
                {"id": "A.02", "allowed_load_unit_types": ["ghost"]},
            ],
            "movement_rule": [{"id": "R1", "allowed_load_unit_types": ["acme_crate"]}],
        }
        errors = cross_refs.check_topology_load_units("h1", entities, {"pallet_euro", "acme_crate"})
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("'ghost'", errors[0])
        self.assertIn("A.01, A.02", errors[0])
