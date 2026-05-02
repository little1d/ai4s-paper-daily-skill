import importlib.util
from pathlib import Path
import sys
import unittest

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
SPEC = importlib.util.spec_from_file_location(
    "ai4s_runner",
    REPO_ROOT / ".codex" / "skills" / "ai4s-paper-daily" / "scripts" / "ai4s_paper_daily.py",
)
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class DedupTests(unittest.TestCase):
    def test_doi_wins(self):
        a = MOD.CandidatePaper(
            source="arxiv",
            source_type="today",
            source_id="1",
            title="Docking Paper",
            authors=[],
            abstract="docking",
            published_date="2026-05-01",
            url="u1",
            pdf_url="",
            venue="arXiv",
            doi="10.1/x",
        )
        b = MOD.CandidatePaper(
            source="curated",
            source_type="history",
            source_id="2",
            title="Docking Paper",
            authors=[],
            abstract="docking",
            published_date="2025-01-01",
            url="u2",
            pdf_url="",
            venue="ICLR",
            doi="10.1/x",
        )
        out = MOD.deduplicate_candidates([a, b])
        self.assertEqual(len(out), 1)

    def test_title_fallback(self):
        a = MOD.CandidatePaper(
            source="arxiv",
            source_type="today",
            source_id="1",
            title="Same Title",
            authors=[],
            abstract="protein representation learning",
            published_date="2026-05-01",
            url="u1",
            pdf_url="",
            venue="arXiv",
        )
        b = MOD.CandidatePaper(
            source="curated",
            source_type="history",
            source_id="2",
            title="Same Title",
            authors=[],
            abstract="protein representation learning",
            published_date="2024-05-01",
            url="u2",
            pdf_url="",
            venue="KDD",
        )
        out = MOD.deduplicate_candidates([a, b])
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
