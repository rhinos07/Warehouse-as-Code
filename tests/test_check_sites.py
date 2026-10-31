"""Tests for tools/check_sites.py - the composition of a site from the
sibling repos. Uses a minimal fake repo set in a temp directory."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import check_sites  # noqa: E402


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


class CheckSitesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        c = "customers/acme"
        self.repos = {key: self.tmp / name for key, name in check_sites.REPO_NAMES.items()}
        topo = self.repos["topology"] / c / "facilities/f1"
        write(topo / "facility.yaml", {"facility": {"id": "F1", "buildings": ["buildings/h1/warehouse.yaml"]}})
        write(topo / "buildings/h1/warehouse.yaml", {"target": {"building": "h1"}})
        alloc = self.repos["allocation"] / c / "facilities/f1"
        write(alloc / "facility.yaml", {"facility": {"id": "f1", "buildings": ["buildings/h1/allocation.yaml"]}})
        write(alloc / "buildings/h1/allocation.yaml", {"allocation": {"id": "h1"}})
        write(self.repos["masterdata"] / c / "company.yaml", {"company": {"id": "acme"}})
        orch = self.repos["orchestration"] / c
        write(orch / "company.yaml", {"company": {"channels": ["channels/web/channel.yaml"]}})
        write(orch / "channels/web/channel.yaml", {"channel": {"order_types": ["order_types/std/order_type.yaml"]}})
        write(orch / "channels/web/order_types/std/order_type.yaml", {"order_type": {"id": "std"}})

        self.sites = self.tmp / "sites"
        self.manifest = {
            "api_version": "warehouse-as-code/v1",
            "site": {
                "id": "acme/f1",
                "topology": {"facility": f"{c}/facilities/f1/facility.yaml"},
                "allocation": {"facility": f"{c}/facilities/f1/facility.yaml"},
                "masterdata": {"company": f"{c}/company.yaml"},
                "order_types": [{"path": f"{c}/channels/web/order_types/std/order_type.yaml", "buildings": ["h1"]}],
            },
        }
        original = check_sites.SITES_DIR
        check_sites.SITES_DIR = self.sites
        self.addCleanup(setattr, check_sites, "SITES_DIR", original)

    def run_check(self, manifest=None, name="acme/f1.yaml"):
        path = self.sites / name
        write(path, manifest or self.manifest)
        return check_sites.check_site(path, self.repos, set(), check_ids=False)

    def test_consistent_site_passes(self):
        self.assertEqual(self.run_check(), [])

    def test_id_must_match_path(self):
        errors = self.run_check(name="acme/other.yaml")
        self.assertTrue(any("must live in" in e for e in errors), errors)

    def test_missing_file_is_reported(self):
        self.manifest["site"]["masterdata"]["company"] = "customers/acme/missing.yaml"
        self.assertTrue(any("not found in MasterData" in e for e in self.run_check()))

    def test_other_customer_path_is_rejected(self):
        self.manifest["site"]["masterdata"]["company"] = "customers/other/company.yaml"
        self.assertTrue(any("not under customers/acme/" in e for e in self.run_check()))

    def test_building_mismatch_is_reported(self):
        write(self.repos["allocation"] / "customers/acme/facilities/f1/buildings/h1/allocation.yaml",
              {"allocation": {"id": "h2"}})
        errors = self.run_check()
        self.assertTrue(any("'h1' is in Topology but has no Allocation" in e for e in errors), errors)
        self.assertTrue(any("'h2' is in Allocation but not in Topology" in e for e in errors), errors)

    def test_unknown_building_on_order_type(self):
        self.manifest["site"]["order_types"][0]["buildings"] = ["h9"]
        self.assertTrue(any("'h9'" in e for e in self.run_check()))

    def test_orphan_order_type_is_reported(self):
        orphan = "customers/acme/channels/web/order_types/orphan/order_type.yaml"
        write(self.repos["orchestration"] / orphan, {"order_type": {"id": "orphan"}})
        self.manifest["site"]["order_types"].append({"path": orphan, "buildings": ["h1"]})
        self.assertTrue(any("not listed by any channel" in e for e in self.run_check()))


if __name__ == "__main__":
    unittest.main()
