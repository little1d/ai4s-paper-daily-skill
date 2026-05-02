from pathlib import Path
import json
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "outputs" / "workflow-test-run"


class SmokeTests(unittest.TestCase):
    def test_dry_run_builds_workflow_outputs(self):
        if RUN_DIR.exists():
            shutil.rmtree(RUN_DIR)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "ai4s_paper_daily.py"),
            "--date", "2026-05-01",
            "--dry-run",
            "--fixtures", str(ROOT / "tests" / "fixtures"),
            "--output-root", str(RUN_DIR),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        base = RUN_DIR / "2026-05-01"
        self.assertTrue((base / "selected.json").exists())
        self.assertTrue((base / "reviewed.json").exists())
        self.assertTrue((base / "report.md").exists())
        self.assertTrue((base / "publish.json").exists())
        reviewed_dir = base / "reviewed"
        self.assertTrue(reviewed_dir.exists())
        reviewed_files = sorted(reviewed_dir.glob("*.md"))
        self.assertGreaterEqual(len(reviewed_files), 5)
        report = (base / "report.md").read_text(encoding="utf-8")
        self.assertIn("当天新论文", report)
        self.assertIn("历史优质论文", report)
        selected = json.loads((base / "selected.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(selected), 10)
        manifest = json.loads((base / "extraction_manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest), 5)
        self.assertIn("fulltext_backend", manifest[0])

    def test_extract_only_emits_manifest_without_reviews(self):
        run_dir = ROOT / "outputs" / "workflow-extract-only"
        if run_dir.exists():
            shutil.rmtree(run_dir)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "ai4s_paper_daily.py"),
            "--date", "2026-05-01",
            "--dry-run",
            "--fixtures", str(ROOT / "tests" / "fixtures"),
            "--output-root", str(run_dir),
            "--extract-only",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
        base = run_dir / "2026-05-01"
        self.assertTrue((base / "extraction_manifest.json").exists())
        manifest = json.loads((base / "extraction_manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest), 5)


if __name__ == "__main__":
    unittest.main()
