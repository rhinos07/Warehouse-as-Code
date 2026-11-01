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
        self.assertTrue(any("'crate'" in m and "customer carrier" in m for m in messages), messages)
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



def write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


TRACKED = {"lot": "required", "expiry": {"tracked": True, "min_remaining_at_receipt_days": 60, "total_shelf_life_days": 270}}
UNTRACKED = {"lot": "none", "expiry": {"tracked": False}}


class TrackingAndFixedBinRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def allocation(self, **files):
        imports = []
        for name, data in files.items():
            write(self.tmp / "strategies" / f"{name}.yaml", data)
            imports.append(f"strategies/{name}.yaml")
        return write(self.tmp / "allocation.yaml", {"allocation": {"id": "h1", "imports": imports}})

    def search(self, rules, items):
        allocation = self.allocation(search_rules={"search_rules": rules})
        return consistency_rules.check_search_rules(allocation, items, select_rule)

    def test_r1_fefo_on_untracked_item_is_error_when_scoped(self):
        rules = [{"id": "S1", "applies_to": {"item_id": "I1"}, "steps": [{"zone": {}, "selection_strategy": "FEFO"}]}]
        findings = self.search(rules, [{"id": "I1", "tracking": UNTRACKED}])
        self.assertEqual([level for level, _ in findings], ["error"])
        self.assertIn("R1", findings[0][1])

    def test_r1_default_rule_is_only_a_warning(self):
        rules = [{"id": "DEF", "steps": [{"zone": {}, "selection_strategy": "FEFO"}]}]
        findings = self.search(rules, [{"id": "I1", "tracking": UNTRACKED}, {"id": "I2", "tracking": TRACKED}])
        self.assertEqual([level for level, _ in findings], ["warning"])

    def test_r2_floor_above_total_shelf_life_is_error(self):
        rules = [{"id": "S1", "applies_to": {"item_id": "I1"},
                  "steps": [{"zone": {}, "selection_strategy": "FEFO", "constraints": {"min_remaining_shelf_life_days": 300}}]}]
        findings = self.search(rules, [{"id": "I1", "tracking": TRACKED}])
        self.assertTrue(any(level == "error" and "R2" in msg for level, msg in findings), findings)

    def test_r2_floor_above_receipt_minimum_is_warning(self):
        rules = [{"id": "S1", "applies_to": {"item_id": "I1"},
                  "steps": [{"zone": {}, "selection_strategy": "FEFO", "constraints": {"min_remaining_shelf_life_days": 90}}]}]
        findings = self.search(rules, [{"id": "I1", "tracking": TRACKED}])
        self.assertEqual([level for level, _ in findings], ["warning"])

    def test_r2_floor_below_receipt_minimum_passes(self):
        rules = [{"id": "S1", "applies_to": {"item_id": "I1"},
                  "steps": [{"zone": {}, "selection_strategy": "FEFO", "constraints": {"min_remaining_shelf_life_days": 30}}]}]
        self.assertEqual(self.search(rules, [{"id": "I1", "tracking": TRACKED}]), [])

    def test_r3_mixed_lots_without_lot_tracking_is_warning(self):
        rules = [{"id": "P1", "applies_to": {"item_id": "I1"},
                  "steps": [{"zone": {}, "placement_strategy": "NEXT_EMPTY", "constraints": {"allow_mixed_lots": False}}]}]
        allocation = self.allocation(putaway_rules={"putaway_rules": rules})
        findings = consistency_rules.check_mixed_lots(allocation, [{"id": "I1", "tracking": UNTRACKED}], select_rule)
        self.assertEqual([level for level, _ in findings], ["warning"])
        findings = consistency_rules.check_mixed_lots(allocation, [{"id": "I1", "tracking": TRACKED}], select_rule)
        self.assertEqual(findings, [])

    def fixed(self, entry):
        allocation = self.allocation(fixed_bin_assignments={"fixed_bin_assignments": [entry]})
        entities = {"storage_point": [{"id": "FIX.1", "allowed_load_unit_types": ["carton"]}]}
        items = [{"id": "I1", "default_uom": "each"}]
        packaging = {"I1": {"each": {"uom": "each"}, "case": {"uom": "case", "load_unit_type": "carton"},
                            "pallet": {"uom": "pallet", "load_unit_type": "pallet_euro"}}}
        return consistency_rules.check_fixed_bins(allocation, entities, items, packaging)

    def test_r8_place_rejects_load_unit(self):
        findings = self.fixed({"item_id": "I1", "storage_point": "FIX.1", "uom": "pallet", "min_qty": 1, "max_qty": 2})
        self.assertTrue(any("R8" in msg and "pallet_euro" in msg for _, msg in findings), findings)

    def test_r8_matching_or_loose_level_passes(self):
        self.assertEqual(self.fixed({"item_id": "I1", "storage_point": "FIX.1", "uom": "case", "min_qty": 1, "max_qty": 2}), [])
        self.assertEqual(self.fixed({"item_id": "I1", "storage_point": "FIX.1", "min_qty": 1, "max_qty": 2}), [])

    def test_r9_unknown_uom(self):
        findings = self.fixed({"item_id": "I1", "storage_point": "FIX.1", "uom": "box", "min_qty": 1, "max_qty": 2})
        self.assertTrue(any("R9" in msg and "'box'" in msg for _, msg in findings), findings)

    def test_packaging_by_item_reads_categories(self):
        company = write(self.tmp / "md/company.yaml", {"company": {"categories": ["categories/a/category.yaml"]}})
        write(self.tmp / "md/categories/a/category.yaml", {"category": {"id": "a", "imports": ["structure/packaging.yaml"]}})
        write(self.tmp / "md/categories/a/structure/packaging.yaml", {"packaging": [
            {"item_id": "I1", "uom_hierarchy": [{"uom": "each", "quantity_of_previous": 1}]}]})
        self.assertEqual(set(consistency_rules.packaging_by_item(company)["I1"]), {"each"})



class OwnerAndSubstitutionRulesTest(unittest.TestCase):
    ENTITIES = {
        "storage_point": [
            {"id": "FIX.1", "storage_type": "FIX", "section": "FIX.SEC_A"},
            {"id": "OPEN.1", "storage_type": "OPEN"},
        ],
        "activity_area": [{"id": "PICK_ALPHA", "bins_from": ["FIX.SEC_A"]}],
    }
    ITEMS = [{"id": "I_ALPHA", "owner": "alpha"}, {"id": "I_BETA", "owner": "beta"}]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def allocation(self, **files):
        imports = []
        for name, data in files.items():
            folder = "structure" if name == "owner_zones" else "strategies"
            write(self.tmp / folder / f"{name}.yaml", data)
            imports.append(f"{folder}/{name}.yaml")
        return write(self.tmp / "allocation.yaml", {"allocation": {"id": "h1", "imports": imports}})

    OWNER_ZONES = {"owner_zones": [{"zone": {"type": "activity_area", "id": "PICK_ALPHA"}, "owners": ["alpha"]}]}

    def test_r6_item_rule_into_foreign_zone(self):
        rules = {"putaway_rules": [
            {"id": "P_BETA", "applies_to": {"item_id": "I_BETA"},
             "steps": [{"zone": {"type": "activity_area", "id": "PICK_ALPHA"}, "placement_strategy": "NEXT_EMPTY"}]},
            {"id": "P_ALPHA", "applies_to": {"item_id": "I_ALPHA"},
             "steps": [{"zone": {"type": "activity_area", "id": "PICK_ALPHA"}, "placement_strategy": "NEXT_EMPTY"}]},
        ]}
        allocation = self.allocation(owner_zones=self.OWNER_ZONES, putaway_rules=rules)
        findings = consistency_rules.check_owner_rules(allocation, self.ENTITIES, self.ITEMS)
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("R6", findings[0][1])
        self.assertIn("I_BETA", findings[0][1])

    def test_r10_fixed_place_in_foreign_zone(self):
        fixed = {"fixed_bin_assignments": [
            {"item_id": "I_BETA", "storage_point": "FIX.1", "min_qty": 1, "max_qty": 2},
            {"item_id": "I_ALPHA", "storage_point": "FIX.1", "min_qty": 1, "max_qty": 2},
            {"item_id": "I_BETA", "storage_point": "OPEN.1", "min_qty": 1, "max_qty": 2},
        ]}
        allocation = self.allocation(owner_zones=self.OWNER_ZONES, fixed_bin_assignments=fixed)
        findings = consistency_rules.check_owner_rules(allocation, self.ENTITIES, self.ITEMS)
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("R10", findings[0][1])
        self.assertIn("fixed_bin_assignments[0]", findings[0][1])

    def test_no_owner_zones_no_findings(self):
        allocation = self.allocation(putaway_rules={"putaway_rules": []})
        self.assertEqual(consistency_rules.check_owner_rules(allocation, self.ENTITIES, self.ITEMS), [])

    def company(self, lifecycle):
        company = write(self.tmp / "md/company.yaml", {"company": {"categories": ["categories/a/category.yaml"]}})
        write(self.tmp / "md/categories/a/category.yaml", {"category": {"id": "a", "imports": ["strategies/lifecycle.yaml"]}})
        write(self.tmp / "md/categories/a/strategies/lifecycle.yaml", {"lifecycle": lifecycle})
        return company

    def order_type(self, allow):
        write(self.tmp / "ot/strategies/shortage_policy.yaml",
              {"shortage_policy": {"default": "backorder", "allow_substitution": allow}})
        return write(self.tmp / "ot/order_type.yaml",
                     {"order_type": {"id": "ot", "imports": ["strategies/shortage_policy.yaml"]}})

    def test_r12_no_substitutes_is_warning(self):
        company = self.company([{"item_id": "I1", "status": "active"}])
        findings = consistency_rules.check_substitution(self.order_type(True), company, [{"id": "I1"}])
        self.assertEqual([level for level, _ in findings], ["warning"])

    def test_r12_unknown_substitute_is_error(self):
        company = self.company([{"item_id": "I1", "status": "seasonal", "substitute_item_id": "I9"}])
        findings = consistency_rules.check_substitution(self.order_type(True), company, [{"id": "I1"}])
        self.assertEqual([level for level, _ in findings], ["error"])

    def test_r12_off_or_valid_passes(self):
        company = self.company([{"item_id": "I1", "status": "seasonal", "substitute_item_id": "I2"}])
        items = [{"id": "I1"}, {"id": "I2"}]
        self.assertEqual(consistency_rules.check_substitution(self.order_type(True), company, items), [])
        self.assertEqual(consistency_rules.check_substitution(self.order_type(False), company, items), [])


if __name__ == "__main__":
    unittest.main()
