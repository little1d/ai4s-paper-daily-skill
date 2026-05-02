import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
SPEC = importlib.util.spec_from_file_location(
    "ai4s_runner",
    REPO_ROOT / ".codex" / "skills" / "ai4s-paper-daily" / "scripts" / "ai4s_paper_daily.py",
)
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class PublishHelperTests(unittest.TestCase):
    def test_load_local_env_sets_missing_values_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text(
                'FEISHU_WIKI_NODE="wiki123"\nAI4S_FULLTEXT_BACKEND=mineru\n',
                encoding="utf-8",
            )
            original = os.environ.get("FEISHU_WIKI_NODE")
            os.environ["FEISHU_WIKI_NODE"] = "keep-existing"
            try:
                loaded = MOD.load_local_env(root)
                self.assertEqual(loaded["FEISHU_WIKI_NODE"], "wiki123")
                self.assertEqual(os.environ["FEISHU_WIKI_NODE"], "keep-existing")
                self.assertEqual(os.environ["AI4S_FULLTEXT_BACKEND"], "mineru")
            finally:
                if original is None:
                    os.environ.pop("FEISHU_WIKI_NODE", None)
                else:
                    os.environ["FEISHU_WIKI_NODE"] = original
                os.environ.pop("AI4S_FULLTEXT_BACKEND", None)

    def test_choose_publish_images_prefers_largest_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            small = root / "small.png"
            medium = root / "medium.png"
            large = root / "large.png"
            small.write_bytes(b"0" * 10)
            medium.write_bytes(b"0" * 120)
            large.write_bytes(b"0" * 240)
            chosen = MOD.choose_publish_images(
                [str(small), str(large), str(medium)],
                limit=2,
                min_bytes=50,
            )
            self.assertEqual(chosen, [str(large), str(medium)])

    def test_publish_to_feishu_inserts_images_after_doc_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            image = run_dir / "figure.png"
            image.write_bytes(b"0" * 100000)
            (run_dir / "reviewed.json").write_text(json.dumps([{
                "index": 1,
                "title": "DiffDock",
                "source_id": "hist-diffdock",
            }]), encoding="utf-8")
            (run_dir / "extraction_manifest.json").write_text(json.dumps([{
                "source_id": "hist-diffdock",
                "image_paths": [str(image)],
            }]), encoding="utf-8")

            def fake_run(cmd, check=False, capture_output=True, text=True, **kwargs):
                if cmd[:3] == ["lark-cli", "docs", "+create"]:
                    return mock.Mock(
                        returncode=0,
                        stdout=json.dumps({"data": {"doc_id": "doc123", "doc_url": "https://example.test/doc123"}}),
                        stderr="",
                    )
                if cmd[:3] == ["lark-cli", "docs", "+media-insert"]:
                    return mock.Mock(returncode=0, stdout=json.dumps({"ok": True}), stderr="")
                raise AssertionError(f"unexpected command: {cmd}")

            with mock.patch.object(MOD.subprocess, "run", side_effect=fake_run):
                status = MOD.publish_to_feishu(run_dir, "# report", skip=False, require=False)

            self.assertEqual(status["status"], "ok")
            self.assertEqual(status["doc_token"], "doc123")
            self.assertEqual(status["image_status"], "ok")
            self.assertEqual(status["inserted_images"], 1)


if __name__ == "__main__":
    unittest.main()
