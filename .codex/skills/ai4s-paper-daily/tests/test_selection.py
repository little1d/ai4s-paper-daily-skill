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


class SelectionTests(unittest.TestCase):
    def test_selection_respects_today_quota_and_total_cap(self):
        today = []
        history = []
        for i in range(6):
            today.append(MOD.score_candidate(MOD.CandidatePaper(
                source="arxiv",
                source_type="today",
                source_id=f"today-{i}",
                title=f"Diffusion for Protein Docking {i}",
                authors=["A"],
                abstract="protein-ligand docking with diffusion and representation learning",
                published_date="2026-05-01",
                url=f"u{i}",
                pdf_url="",
                venue="arXiv",
            )))
        for i in range(6):
            history.append(MOD.score_candidate(MOD.CandidatePaper(
                source="curated",
                source_type="history",
                source_id=f"hist-{i}",
                title=f"Protein representation benchmark {i}",
                authors=["B"],
                abstract="protein representation learning benchmark for biological sequences",
                published_date="2024-01-01",
                url=f"h{i}",
                pdf_url="",
                venue="KDD",
            )))
        selected = MOD.select_final_candidates(today, history, max_total=10, today_min=3, today_max=5)
        today_count = sum(1 for x in selected if x.paper.source_type == "today")
        history_count = sum(1 for x in selected if x.paper.source_type == "history")
        self.assertLessEqual(len(selected), 10)
        self.assertGreaterEqual(today_count, 3)
        self.assertLessEqual(today_count, 5)
        self.assertGreater(history_count, 0)

    def test_fulltext_gate_blocks_missing_text(self):
        candidate = MOD.score_candidate(MOD.CandidatePaper(
            source="arxiv",
            source_type="today",
            source_id="missing-fulltext",
            title="Docking with Flow Matching",
            authors=["A"],
            abstract="protein-ligand docking with flow matching",
            published_date="2026-05-01",
            url="u",
            pdf_url="",
            venue="arXiv",
        ))
        reviewed = MOD.review_candidate(candidate, "", index=1)
        self.assertIsNone(reviewed)


if __name__ == "__main__":
    unittest.main()
