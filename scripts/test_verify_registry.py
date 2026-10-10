#!/usr/bin/env python3
"""Offline negative controls for accidental SK1 task collision."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import verify_registry


REPO=Path(__file__).resolve().parents[1]


class RegistryGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        source=json.loads((REPO/"experiments/registry.json").read_text(encoding="utf-8"))
        self.records=source
        for r in source["records"]:
            if r["git_ref"]=="main":
                p=self.root/r["code_path"]
                p.mkdir(parents=True)
                (p/"README.md").write_text("legacy fixture")
                (p/"run.py").write_text("print('ok')")
        self.write()

    def write(self):
        f=self.root/"experiments/registry.json"
        f.parent.mkdir(exist_ok=True,parents=True)
        f.write_text(json.dumps(self.records))

    def check(self):
        self.write()
        return verify_registry.verify(self.root)

    def test_real_repo_passes(self):
        self.assertEqual(verify_registry.verify(REPO),[])

    def test_baseline_fixture_passes(self):
        self.assertEqual(self.check(),[])

    def test_duplicate_experiment_id_rejected(self):
        self.records["records"].append(copy.deepcopy(self.records["records"][0]))
        self.assertTrue(any("duplicate experiment key" in err for err in self.check()))

    def test_duplicate_task_id_rejected(self):
        r=copy.deepcopy(self.records["records"][5])
        r["key"]="SK1-CFB-DIAG-PUB-T-952"
        r["type"]="DIAG"
        r["code_path"]="experiments/cfb/diag/pub-t-952"
        self.records["records"].append(r)
        self.assertTrue(any("duplicate canonical Notion Task ID" in err for err in self.check()))

    def test_duplicate_notion_task_link_rejected(self):
        self.records["records"][7]["task_notion"]=self.records["records"][6]["task_notion"]
        self.assertTrue(any("duplicate Notion task URL" in err for err in self.check()))

    def test_unregistered_executable_rejected(self):
        p=self.root/"experiments/quill/val/pub-t-999"
        p.mkdir(parents=True)
        (p/"run.py").write_text("pass")
        self.assertTrue(any("unregistered" in err for err in self.check()))

    def test_parked_task_code_rejected(self):
        p=self.root/"experiments/quill/exp/pub-t-953"
        p.mkdir(parents=True)
        (p/"run.py").write_text("pass")
        self.assertTrue(any("parked task" in err for err in self.check()))

    def test_path_traversal_rejected(self):
        self.records["records"][6]["code_path"]="experiments/../../private"
        self.assertTrue(any("unsafe" in err for err in self.check()))

    def test_future_legacy_number_forbidden(self):
        r=copy.deepcopy(self.records["records"][0])
        r.update(key="SK1-EXP-006",code_path="experiments/sk1-exp-006")
        p=self.root/r["code_path"]
        p.mkdir(parents=True)
        (p/"README.md").write_text("wrong")
        self.records["records"].append(r)
        self.assertTrue(any("new legacy numbered ID forbidden" in err for err in self.check()))

    def test_claimed_missing_branch_rejected(self):
        self.records["records"][6]["state"]="claimed"
        self.assertTrue(any("must use explicit task branch" in err for err in self.check()))


if __name__=="__main__":
    unittest.main()
