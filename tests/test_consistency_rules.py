"""Tests for tools/consistency_rules.py - R11, R4, R5. They check for
configuration the runtime can never satisfy (error) or always overrides
(warning), not the per-task enforcement the runtime does itself."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import consistency_rules  # noqa: E402


def select_rule(rules, item):
    """Minimal stand-in for Allocation's precedence: item_id, else default."""
    for rule in rules:
        if (rule.get("applies_to") or {}).get("item_id") == item["id"]:
            return rule
    return next((r for r in rules if not r.get("applies_to")), None)


ENTITIES = {
    "storage_type": [
        {"id": "AMB"}, {"id": "COLD"}, {"id": "CHAN", "homogeneity_required": True},
    ],
    "storage_point": [
        {"id": "AMB.1", "storage_type": "AMB", "storage_condition": "ambient", "allowed_load_unit_types": ["pallet_euro"]},
        {"id": "COLD.1", "storage_type": "COLD", "storage_condition": "chilled", "allowed_load_unit_types": ["pallet_euro"]},
        {"id": "CHAN.1", "storage_type": "CHAN", "storage_condition": "ambient", "allowed_load_unit_types": ["pallet_euro"]},
    ],
    "activity_area": [{"id": "AREA_COLD", "bins_from": ["COLD"]}],
}
CATALOG = {"pallet_euro", "carton"}


class ConsistencyRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def run_rules(self, rules, items):
        (self.tmp / "strategies").mkdir(exist_ok=True)
        (self.tmp / "strategies/putaway_rules.yaml").write_text(yaml.safe_dump({"putaway_rules": rules}), encoding="utf-8")
        allocation = self.tmp / "allocation.yaml"
        allocation.write_text(yaml.safe_dump({"allocation": {"id": "h1", "imports": ["strategies/putaway_rules.yaml"]}}), encoding="utf-8")
        return consistency_rules.check_putaway_rules(allocation, ENTITIES, items, CATALOG, select_rule)

    def step(self, zone_type, zone_id, **constraints):
        return {"zone": {"type": zone_type, "id": zone_id}, "placement_strategy": "NEXT_EMPTY", "constraints": constraints}

    def test_r11_no_place_with_condition_is_an_error(self):
        rules = [{"id": "DEF", "steps": [self.step("storage_type", "AMB")]}]
        findings = self.run_rules(rules, [{"id": "I1", "storage_condition": "chilled"}])
        self.assertTrue(any(level == "error" and "R11" in msg and "I1" in msg for level, msg in findings), findings)

    def test_r11_mixed_zone_list_is_fine(self):
        # The runtime filters by condition; one fitting step is enough.
        rules = [{"id": "DEF", "steps": [self.step("storage_type", "AMB"), self.step("activity_area", "AREA_COLD")]}]
        self.assertEqual(self.run_rules(rules, [{"id": "I1", "storage_condition": "chilled"}]), [])

    def test_r11_uses_the_rule_chosen_for_the_item(self):
        rules = [
            {"id": "DEF", "steps": [self.step("storage_type", "AMB")]},
            {"id": "COLD_ITEM", "applies_to": {"item_id": "I1"}, "steps": [self.step("storage_type", "COLD")]},
        ]
        findings = self.run_rules(rules, [{"id": "I1", "storage_condition": "chilled"}, {"id": "I2", "storage_condition": "ambient"}])
        self.assertEqual(findings, [])

    def test_r11_unknown_point_condition_is_not_an_error(self):
        entities_point = {"id": "X.1", "storage_type": "X"}
        ENTITIES["storage_point"].append(entities_point)
        self.addCleanup(ENTITIES["storage_point"].remove, entities_point)
        rules = [{"id": "DEF", "steps": [self.step("storage_type", "X")]}]
        self.assertEqual(self.run_rules(rules, [{"id": "I1", "storage_condition": "frozen"}]), [])

    def test_r4_unknown_and_unaccepted_load_units(self):
        rules = [{"id": "DEF", "steps": [self.step("storage_type", "AMB", load_unit_types=["crate", "carton"])]}]
        messages = [msg for level, msg in self.run_rules(rules, []) if level == "error"]
        self.assertTrue(any("'crate'" in m and "catalog" in m for m in messages), messages)
        self.assertTrue(any("'carton'" in m and "accepts" in m for m in messages), messages)

    def test_r5_mixed_items_on_homogeneous_zone_is_a_warning(self):
        rules = [{"id": "DEF", "steps": [self.step("storage_type", "CHAN", allow_mixed_items=True)]}]
        findings = self.run_rules(rules, [])
        self.assertEqual([level for level, _ in findings], ["warning"])
        self.assertIn("R5", findings[0][1])

    def test_r5_not_raised_on_mixed_zone(self):
        rules = [{"id": "DEF", "steps": [self.step("storage_type", "AMB", allow_mixed_items=True)]}]
        self.assertEqual(self.run_rules(rules, []), [])


class RealPrecedenceTest(unittest.TestCase):
    def test_loads_allocation_select_rule(self):
        allocation = next((p for p in REPO_ROOT.parent.iterdir() if p.name.lower() == "allocation-as-code"), None)
        if allocation is None:
            self.skipTest("Allocation-as-Code not checked out next to this repo")
        select = consistency_rules.load_precedence(allocation)
        rules = [{"id": "D"}, {"id": "C", "applies_to": {"category": "c"}}]
        self.assertEqual(select(rules, {"id": "I", "category": "c"})["id"], "C")


if __name__ == "__main__":
    unittest.main()
