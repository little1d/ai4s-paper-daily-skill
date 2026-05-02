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


class RenderingTests(unittest.TestCase):
    def test_review_markdown_uses_speech_style_sections(self):
        candidate = MOD.score_candidate(MOD.CandidatePaper(
            source="curated",
            source_type="history",
            source_id="hist-1",
            title="DiffDock: Diffusion Steps, Twists, and Turns for Molecular Docking",
            authors=["A", "B"],
            abstract="Diffusion-based protein-ligand docking with uncertainty estimates.",
            published_date="2023-01-01",
            url="https://example.com",
            pdf_url="",
            venue="ICLR",
            fulltext_text="Introduction We propose a diffusion docking framework. Method The model combines confidence estimation with pose refinement. Experiments We evaluate on Docking Benchmark and outperform baselines with better top-1 success. Conclusion The method is strong for docking.",
        ))
        reviewed = MOD.review_candidate(candidate, MOD.LoadedFulltext(text=candidate.paper.fulltext_text, backend="fixture"), index=1)
        self.assertIsNotNone(reviewed)
        text = MOD.render_review_markdown(reviewed)
        self.assertIn("| 字段 | 内容 |", text)
        self.assertIn("全文解析", text)
        self.assertIn("### 📌 简介", text)
        self.assertIn("### ☠️ 毒舌点评", text)
        self.assertIn("### 🔧 技术方案", text)
        self.assertIn("### 📊 实验结果", text)
        self.assertIn("### ⭐ 评分:", text)

    def test_review_candidate_requires_fulltext_sections(self):
        candidate = MOD.score_candidate(MOD.CandidatePaper(
            source="curated",
            source_type="history",
            source_id="hist-2",
            title="Weak Abstract-Only Paper",
            authors=["A"],
            abstract="A diffusion model for docking.",
            published_date="2024-01-01",
            url="https://example.com",
            pdf_url="",
            venue="ICLR",
            fulltext_text="This paper proposes a diffusion model for docking and reports some results.",
        ))
        reviewed = MOD.review_candidate(candidate, MOD.LoadedFulltext(text=candidate.paper.fulltext_text, backend="fixture"), index=1)
        self.assertIsNone(reviewed)


if __name__ == "__main__":
    unittest.main()
