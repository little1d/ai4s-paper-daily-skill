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


class RelevanceTests(unittest.TestCase):
    def test_cross_domain_method_scores_higher(self):
        strong = MOD.CandidatePaper(
            source="arxiv",
            source_type="today",
            source_id="t1",
            title="Flow Matching for Protein Sequence Design",
            authors=["A"],
            abstract="We use flow matching and protein language modeling for sequence design.",
            published_date="2026-05-01",
            url="u1",
            pdf_url="",
            venue="arXiv",
        )
        weak = MOD.CandidatePaper(
            source="biorxiv",
            source_type="today",
            source_id="t2",
            title="Cellular imaging of macrophage activation",
            authors=["B"],
            abstract="We study macrophage activation in cell biology.",
            published_date="2026-05-01",
            url="u2",
            pdf_url="",
            venue="bioRxiv",
        )
        strong_score = MOD.score_candidate(strong)
        weak_score = MOD.score_candidate(weak)
        self.assertGreater(strong_score.relevance_score, weak_score.relevance_score)
        self.assertEqual(strong_score.primary_topic, "protein")

    def test_representation_keyword_supported(self):
        paper = MOD.CandidatePaper(
            source="arxiv",
            source_type="today",
            source_id="t3",
            title="Representation Learning for Molecular Property Prediction",
            authors=["A"],
            abstract="We benchmark representation learning for molecular property prediction and drug discovery.",
            published_date="2026-05-01",
            url="u3",
            pdf_url="",
            venue="arXiv",
        )
        scored = MOD.score_candidate(paper)
        self.assertIn("representation", scored.method_tags)
        self.assertEqual(scored.primary_topic, "small-molecule")


if __name__ == "__main__":
    unittest.main()
