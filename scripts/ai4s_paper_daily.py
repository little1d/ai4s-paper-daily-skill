#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
MINERU_CACHE_ROOT = REPO_ROOT / ".cache" / "mineru-models"

ARXIV_PAPERS_COOL_CATEGORIES = ["q-bio.BM", "q-bio.QM", "cs.LG", "cs.AI"]
ARXIV_FALLBACK_QUERY = 'all:"protein" OR all:"small molecule" OR all:docking OR all:diffusion OR all:"flow matching" OR all:"representation learning" OR all:"drug discovery"'
USER_AGENT = "ai4s-paper-daily/0.2"
PREFERRED_HISTORY_VENUES = {"iclr", "neurips", "icml", "kdd", "nature machine intelligence", "bioinformatics", "jcim", "jctc", "nature communications"}
UNWANTED_TERMS = ["microscopy", "neuroscience", "fmri", "speech perception", "plant", "macrophage activation"]
TOPIC_KEYWORDS = {
    "protein": ["protein", "sequence design", "protein language model", "peptide", "enzyme", "antibody"],
    "small-molecule": ["small molecule", "molecular", "drug discovery", "property prediction", "admet", "scaffold", "conformation"],
    "docking": ["docking", "protein-ligand", "binding affinity", "pose", "virtual screening"],
}
METHOD_KEYWORDS = {
    "diffusion": ["diffusion", "denoising diffusion", "latent diffusion"],
    "flow-matching": ["flow matching"],
    "representation": ["representation learning", "representation", "contrastive", "foundation model", "language model", "post training", "pretraining", "transformer", "graph neural network", "gnn"],
}
TOPIC_DISPLAY = {
    "protein": "蛋白质",
    "small-molecule": "小分子",
    "docking": "分子 docking",
    "other-ai4s-relevant": "AI4S 交叉",
}
SOURCE_TYPE_DISPLAY = {
    "today": "当天新论文",
    "history": "历史优质论文",
}
SECTION_ALIASES = {
    "introduction": ["introduction", "background"],
    "method": ["method", "methods", "approach", "approaches", "methodology", "framework", "model"],
    "training": ["training", "training details", "implementation details", "optimization", "optimization details", "pretraining", "pre-training", "post training", "post-training"],
    "experiments": ["experiment", "experiments", "evaluation", "evaluations", "results", "benchmark", "empirical study"],
    "conclusion": ["conclusion", "conclusions", "discussion", "limitations", "final remarks"],
}
ARCHITECTURE_HINTS = [
    (r"\bdiffusion\b", "以扩散/去噪过程为主干"),
    (r"\bflow[-\s]+matching\b", "以 Flow Matching 轨迹建模为主干"),
    (r"\bequivariant\b|\bse\(3\)\b", "显式利用几何等变性"),
    (r"\bgraph neural network\b|\bgnn\b", "把图神经网络当成核心编码器"),
    (r"\btransformer\b", "主干里有 Transformer 表征层"),
    (r"\bprotein language model\b|\blanguage model\b|\bfoundation model\b", "借助预训练语言模型/基础模型表征"),
]
MODULE_HINTS = [
    (r"\bconfidence\b", "带 confidence estimation / reranking"),
    (r"\brank(?:ing)?\b", "显式做 ranking / candidate selection"),
    (r"\bbinding affinity\b|\baffinity\b", "把 affinity 作为核心监督或辅助信号"),
    (r"\bcross[-\s]?attention\b", "含跨模态 / cross-attention 交互"),
    (r"\bdenois(?:e|ing)\b", "通过逐步 denoising 逼近目标结构"),
    (r"\bpose\b", "直接围绕 docking pose 建模"),
]
TRAINING_HINTS = [
    (r"\bpre[-\s]?train(?:ing)?\b", "带预训练阶段"),
    (r"\bpost[-\s]?training\b", "显式做 post-training / task adaptation"),
    (r"\bcontrastive\b", "包含 contrastive learning"),
    (r"\bdistill(?:ation)?\b", "使用蒸馏信号"),
    (r"\bfine[-\s]?tun(?:e|ing)\b", "有独立微调阶段"),
    (r"\bself[-\s]?supervised\b", "含自监督目标"),
    (r"\baugmentation\b|\baugmented\b", "使用数据增强"),
]
LOSS_HINTS = [
    (r"\bcross entropy\b", "cross-entropy"),
    (r"\bmse\b|\bl2\b", "MSE/L2"),
    (r"\bmae\b|\bl1\b", "MAE/L1"),
    (r"\branking loss\b", "ranking loss"),
    (r"\bcontrastive loss\b", "contrastive loss"),
    (r"\bdenois(?:e|ing) objective\b", "denoising objective"),
    (r"\bkl\b|\bkl divergence\b", "KL regularization"),
]
DATASET_HINTS = [
    (r"\bpdbbind\b", "PDBBind"),
    (r"\bcrossdocked\b", "CrossDocked"),
    (r"\bbindingdb\b", "BindingDB"),
    (r"\bmoleculenet\b", "MoleculeNet"),
    (r"\bqm9\b", "QM9"),
    (r"\bpcqm4m\b", "PCQM4M"),
    (r"\bchembl\b", "ChEMBL"),
    (r"\bgeom\b", "GEOM"),
    (r"\buniprot\b", "UniProt"),
    (r"\bswissprot\b", "SwissProt"),
    (r"\bproteinnet\b", "ProteinNet"),
    (r"\btape\b", "TAPE"),
]
RESULT_HINTS = [
    (r"\bablation\b", "做了 ablation"),
    (r"\bbaseline\b", "和强 baseline 对比"),
    (r"\boutperform\b|\bsota\b|\bstate-of-the-art\b", "主结果明确优于已有方法"),
    (r"\btop[-\s]?1\b", "报告了 top-1 类指标"),
    (r"\bauc\b", "报告了 AUC"),
    (r"\brmse\b", "报告了 RMSE"),
    (r"\bmae\b", "报告了 MAE"),
    (r"\bsuccess rate\b", "报告了 success rate"),
    (r"\bzero[-\s]?shot\b", "测了 zero-shot / transfer"),
]
INNOVATION_HINTS = [
    (r"\bwe propose\b", "明确提出了新框架"),
    (r"\bnovel\b", "强调方法层面的 novelty"),
    (r"\bfirst\b", "把“first”当卖点"),
    (r"\bunified\b", "试图统一多个子问题"),
    (r"\bend-to-end\b", "主打 end-to-end 训练"),
    (r"\bmultimodal\b", "显式做多模态交互"),
    (r"\buncertainty\b|\bconfidence\b", "把 uncertainty/confidence 纳入决策链路"),
]


@dataclass
class CandidatePaper:
    source: str
    source_type: str
    source_id: str
    title: str
    authors: list[str]
    abstract: str
    published_date: str
    url: str
    pdf_url: str
    venue: str
    doi: str = ""
    raw_tags: list[str] | None = None
    code_url: str = ""
    demo_url: str = ""
    fulltext_path: str = ""
    fulltext_text: str = ""


@dataclass
class ScoredCandidate:
    paper: CandidatePaper
    relevance_score: int
    primary_topic: str
    topic_tags: list[str]
    method_tags: list[str]
    relevance_reason: str


@dataclass
class ReviewedPaper:
    index: int
    source_type: str
    source: str
    source_id: str
    title: str
    authors: list[str]
    venue: str
    published_date: str
    url: str
    pdf_url: str
    code_url: str
    demo_url: str
    primary_topic: str
    topic_tags: list[str]
    method_tags: list[str]
    relevance_score: int
    score: int
    score_reason: str
    worth_reading: str
    summary_cn: str
    roast_cn: str
    architecture_cn: list[str]
    innovation_cn: list[str]
    training_cn: list[str]
    experiments_cn: list[str]
    fulltext_status: str
    fulltext_backend: str
    source_label: str
    evidence: dict[str, str]


@dataclass
class LoadedFulltext:
    text: str
    backend: str
    path: str = ""
    markdown_path: str = ""
    artifact_dir: str = ""
    image_paths: list[str] | None = None


class SourceFetchError(Exception):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI4S workflow-first paper daily runner")
    p.add_argument("--date", default="today", help="YYYY-MM-DD or 'today'")
    p.add_argument("--output-root", default="outputs/daily-runs")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--fixtures", help="Fixture directory for dry-run")
    p.add_argument("--history-pool", default="data/history_pool.json")
    p.add_argument("--skip-feishu", action="store_true")
    p.add_argument("--require-feishu", action="store_true")
    p.add_argument("--max-total", type=int, default=10)
    p.add_argument("--today-min", type=int, default=3)
    p.add_argument("--today-max", type=int, default=5)
    p.add_argument("--fulltext-backend", choices=["mineru"], default=os.environ.get("AI4S_FULLTEXT_BACKEND", "mineru"))
    p.add_argument("--extract-only", action="store_true", help="only select papers and parse fulltext assets for skill-driven review")
    return p.parse_args(argv)


def resolve_date(raw: str) -> dt.date:
    if raw == "today":
        return dt.date.today()
    return dt.date.fromisoformat(raw)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_url(url: str, *, accept: str | None = None) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **({"Accept": accept} if accept else {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read(), dict(resp.headers.items())


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title.lower())).strip()


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if s.strip()]


def keyword_pattern(keyword: str) -> str:
    parts = re.findall(r"[a-z0-9]+", keyword.lower())
    if not parts:
        return re.escape(keyword.lower())
    if len(parts) == 1:
        return rf"\b{re.escape(parts[0])}\b"
    sep = r"[-\s]+"
    return rf"\b{sep.join(re.escape(part) for part in parts)}\b"


def find_keyword_hits(hay: str, groups: dict[str, list[str]]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for label, keywords in groups.items():
        matched = [kw for kw in keywords if re.search(keyword_pattern(kw), hay)]
        if matched:
            hits[label] = matched
    return hits


def score_candidate(paper: CandidatePaper) -> ScoredCandidate:
    hay = "\n".join([
        paper.title,
        paper.abstract,
        paper.venue,
        " ".join(paper.raw_tags or []),
    ]).lower()
    topic_hits = find_keyword_hits(hay, TOPIC_KEYWORDS)
    method_hits = find_keyword_hits(hay, METHOD_KEYWORDS)
    score = 0
    score += sum(3 for _ in topic_hits)
    score += sum(2 for _ in method_hits)
    if topic_hits and method_hits:
        score += 2
    if paper.source_type == "history" and paper.venue.lower() in PREFERRED_HISTORY_VENUES:
        score += 1
    penalties = [term for term in UNWANTED_TERMS if term in hay]
    score -= len(penalties) * 2
    topic_tags = sorted(topic_hits)
    method_tags = sorted(method_hits)
    primary_topic = topic_tags[0] if topic_tags else "other-ai4s-relevant"
    reason_bits = []
    if topic_hits:
        reason_bits.append("主题=" + ", ".join(f"{k}:{'/'.join(v[:2])}" for k, v in topic_hits.items()))
    if method_hits:
        reason_bits.append("方法=" + ", ".join(f"{k}:{'/'.join(v[:2])}" for k, v in method_hits.items()))
    if penalties:
        reason_bits.append("降权=" + ", ".join(penalties[:3]))
    if not reason_bits:
        reason_bits.append("未命中核心 AI4S 主题与方法交叉")
    return ScoredCandidate(
        paper=paper,
        relevance_score=max(score, 0),
        primary_topic=primary_topic,
        topic_tags=topic_tags,
        method_tags=method_tags,
        relevance_reason="; ".join(reason_bits),
    )


def deduplicate_candidates(candidates: list[CandidatePaper]) -> list[CandidatePaper]:
    kept: dict[str, CandidatePaper] = {}
    for paper in candidates:
        key = paper.doi.strip().lower() or normalize_title(paper.title) or f"{paper.source}:{paper.source_id}".lower()
        if key not in kept:
            kept[key] = paper
    return list(kept.values())


def load_candidates_from_json(path: Path) -> list[CandidatePaper]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CandidatePaper(**item) for item in data]


def is_placeholder_candidate(paper: CandidatePaper) -> bool:
    hay = " ".join([
        paper.title,
        " ".join(paper.authors),
        paper.url,
        paper.pdf_url,
        paper.abstract,
    ]).lower()
    return any(token in hay for token in ["example.com", "starter pool", "placeholder", "curated starter-pool"])


def filter_real_candidates(candidates: list[CandidatePaper]) -> list[CandidatePaper]:
    return [paper for paper in candidates if not is_placeholder_candidate(paper)]


def resolve_candidate_fulltext_path(paper: CandidatePaper, base_dir: Path | None) -> str:
    if paper.fulltext_text:
        return paper.fulltext_text
    if paper.fulltext_path:
        candidate_path = Path(paper.fulltext_path)
        if base_dir is not None and not candidate_path.is_absolute():
            candidate_path = base_dir / candidate_path
        if candidate_path.exists():
            return candidate_path.read_text(encoding="utf-8")
    return ""


def discover_arxiv_ids_from_papers_cool(target_date: dt.date, raw_dir: Path) -> list[str]:
    ids: set[str] = set()
    capture: dict[str, Any] = {"categories": {}, "target_date": target_date.isoformat()}
    for category in ARXIV_PAPERS_COOL_CATEGORIES:
        url = f"https://papers.cool/arxiv/{category}"
        try:
            body, _ = fetch_url(url, accept="text/html")
            html = body.decode("utf-8", "ignore")
            found = sorted(set(re.findall(r"\b\d{4}\.\d{4,5}(?:v\d+)?\b", html)))
            capture["categories"][category] = {"url": url, "ids": found}
            ids.update(found)
        except Exception as exc:
            capture["categories"][category] = {"url": url, "error": str(exc), "ids": []}
    write_json(raw_dir / "papers_cool_discovery.json", capture)
    return sorted(ids)


def fetch_today_arxiv_candidates(target_date: dt.date, raw_dir: Path) -> list[CandidatePaper]:
    ids = discover_arxiv_ids_from_papers_cool(target_date, raw_dir)
    from_current_batch = bool(ids)
    if ids:
        query = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": ",".join(ids[:100])})
    else:
        query = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
            "search_query": ARXIV_FALLBACK_QUERY,
            "start": 0,
            "max_results": 100,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
    body, _ = fetch_url(query, accept="application/atom+xml")
    (raw_dir / "api.xml").write_bytes(body)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(body)
    out: list[CandidatePaper] = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        published = (entry.findtext("atom:published", default="", namespaces=ns) or "")[:10]
        if not from_current_batch and published and published != target_date.isoformat():
            continue
        entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        source_id = entry_id.rsplit("/", 1)[-1]
        authors = [a.findtext("atom:name", default="", namespaces=ns).strip() for a in entry.findall("atom:author", ns)]
        cats = [c.attrib.get("term", "") for c in entry.findall("atom:category", ns)]
        doi = ""
        doi_el = entry.find("arxiv:doi", ns)
        if doi_el is not None and doi_el.text:
            doi = doi_el.text.strip()
        out.append(CandidatePaper(
            source="arxiv",
            source_type="today",
            source_id=source_id,
            title=title,
            authors=authors,
            abstract=abstract,
            published_date=published or target_date.isoformat(),
            url=entry_id,
            pdf_url=f"https://arxiv.org/pdf/{source_id}.pdf" if source_id else "",
            venue="arXiv",
            doi=doi,
            raw_tags=cats,
        ))
    return out


def fetch_keyword_today_candidates(target_date: dt.date, raw_dir: Path) -> list[CandidatePaper]:
    query = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": ARXIV_FALLBACK_QUERY,
        "start": 0,
        "max_results": 100,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    body, _ = fetch_url(query, accept="application/atom+xml")
    (raw_dir / "keyword_api.xml").write_bytes(body)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(body)
    out: list[CandidatePaper] = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        published = (entry.findtext("atom:published", default="", namespaces=ns) or "")[:10]
        if published and published != target_date.isoformat():
            continue
        entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        source_id = entry_id.rsplit("/", 1)[-1]
        authors = [a.findtext("atom:name", default="", namespaces=ns).strip() for a in entry.findall("atom:author", ns)]
        cats = [c.attrib.get("term", "") for c in entry.findall("atom:category", ns)]
        out.append(CandidatePaper(
            source="arxiv-keyword",
            source_type="today",
            source_id=source_id,
            title=title,
            authors=authors,
            abstract=abstract,
            published_date=published or target_date.isoformat(),
            url=entry_id,
            pdf_url=f"https://arxiv.org/pdf/{source_id}.pdf" if source_id else "",
            venue="arXiv",
            raw_tags=cats,
        ))
    return out



def choose_today_candidates(today: list[ScoredCandidate], *, today_min: int, today_max: int) -> list[ScoredCandidate]:
    ranked = sorted(today, key=lambda x: (x.relevance_score, len(x.method_tags), len(x.topic_tags), x.paper.published_date), reverse=True)
    strict = [paper for paper in ranked if paper.relevance_score >= 5 and paper.primary_topic != "other-ai4s-relevant"]
    relaxed = [paper for paper in ranked if paper.relevance_score >= 3]
    picked = strict[:today_max]
    if len(picked) < min(today_min, len(relaxed)):
        for paper in relaxed:
            if paper not in picked:
                picked.append(paper)
            if len(picked) >= min(today_max, max(today_min, len(strict))):
                break
    return picked[:today_max]


def choose_history_candidates(history: list[ScoredCandidate], *, remaining: int, seen_titles: set[str], covered_topics: set[str]) -> list[ScoredCandidate]:
    ranked = sorted(history, key=lambda x: (x.relevance_score, len(x.method_tags), x.paper.venue.lower() in PREFERRED_HISTORY_VENUES), reverse=True)
    chosen: list[ScoredCandidate] = []
    local_topics = set(covered_topics)
    while ranked and len(chosen) < remaining:
        best_idx = 0
        best_value = None
        for idx, cand in enumerate(ranked):
            bonus = 1 if cand.primary_topic not in local_topics else 0
            value = (cand.relevance_score + bonus, len(cand.method_tags), cand.paper.venue.lower() in PREFERRED_HISTORY_VENUES)
            if best_value is None or value > best_value:
                best_idx = idx
                best_value = value
        paper = ranked.pop(best_idx)
        if normalize_title(paper.paper.title) in seen_titles:
            continue
        if paper.relevance_score < 4:
            continue
        chosen.append(paper)
        seen_titles.add(normalize_title(paper.paper.title))
        local_topics.add(paper.primary_topic)
    return chosen


def select_final_candidates(today: list[ScoredCandidate], history: list[ScoredCandidate], *, max_total: int, today_min: int, today_max: int) -> list[ScoredCandidate]:
    selected_today = choose_today_candidates(today, today_min=today_min, today_max=today_max)
    seen_titles = {normalize_title(c.paper.title) for c in selected_today}
    covered_topics = {c.primary_topic for c in selected_today}
    remaining = max(max_total - len(selected_today), 0)
    selected_history = choose_history_candidates(history, remaining=remaining, seen_titles=seen_titles, covered_topics=covered_topics)
    selected = selected_today + selected_history
    return sorted(selected, key=lambda x: (0 if x.paper.source_type == "today" else 1, -x.relevance_score, x.paper.title.lower()))[:max_total]


def clean_mineru_markdown(text: str) -> str:
    cleaned = text.replace("\r", "\n")
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"<details>.*?</details>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"`{3,}.*?`{3,}", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def find_mineru_images(output_dir: Path) -> list[str]:
    out: list[str] = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for path in sorted(output_dir.rglob(ext)):
            if path.is_file():
                out.append(str(path))
    return out


def load_mineru_markdown(output_dir: Path) -> tuple[str, str]:
    md_candidates = sorted(
        [p for p in output_dir.rglob("*.md") if p.is_file()],
        key=lambda p: (p.stat().st_size, len(p.parts)),
        reverse=True,
    )
    for path in md_candidates:
        text = clean_mineru_markdown(path.read_text(encoding="utf-8", errors="ignore"))
        if text.strip():
            return text, str(path)
    return "", ""


def extract_with_mineru(pdf_path: Path, cache_dir: Path, stem: str) -> LoadedFulltext:
    if not shutil.which("mineru"):
        return LoadedFulltext(text="", backend="mineru-missing")
    output_dir = ensure_dir(cache_dir / "mineru" / stem)
    modelscope_cache = ensure_dir(MINERU_CACHE_ROOT / "modelscope")
    mineru_env = {
        **os.environ,
        "MINERU_MODEL_SOURCE": os.environ.get("MINERU_MODEL_SOURCE", "modelscope"),
        "MODELSCOPE_CACHE": os.environ.get("MODELSCOPE_CACHE", str(modelscope_cache)),
        "MINERU_DEVICE_MODE": os.environ.get("MINERU_DEVICE_MODE", "cpu"),
    }
    if os.environ.get("HF_HOME"):
        mineru_env["HF_HOME"] = os.environ["HF_HOME"]
    if os.environ.get("HUGGINGFACE_HUB_CACHE"):
        mineru_env["HUGGINGFACE_HUB_CACHE"] = os.environ["HUGGINGFACE_HUB_CACHE"]
    proc = subprocess.run(
        ["mineru", "-p", str(pdf_path), "-o", str(output_dir), "-b", "pipeline"],
        check=False,
        capture_output=True,
        text=True,
        env=mineru_env,
    )
    if proc.returncode != 0:
        return LoadedFulltext(text="", backend="mineru-failed", path=str(pdf_path), artifact_dir=str(output_dir))
    text, markdown_path = load_mineru_markdown(output_dir)
    return LoadedFulltext(
        text=text,
        backend="mineru" if text.strip() else "mineru-empty",
        path=str(pdf_path),
        markdown_path=markdown_path,
        artifact_dir=str(output_dir),
        image_paths=find_mineru_images(output_dir),
    )


def download_pdf(pdf_url: str, cache_dir: Path, stem: str) -> Path | None:
    if not pdf_url:
        return None
    ensure_dir(cache_dir)
    pdf_path = cache_dir / f"{stem}.pdf"
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        return pdf_path
    try:
        body, _ = fetch_url(pdf_url, accept="application/pdf")
        pdf_path.write_bytes(body)
        return pdf_path
    except Exception:
        return None


def load_fulltext(scored: ScoredCandidate, *, run_dir: Path, base_dir: Path | None, backend_preference: str) -> LoadedFulltext:
    direct = resolve_candidate_fulltext_path(scored.paper, base_dir)
    if direct.strip():
        return LoadedFulltext(text=direct, backend="fixture" if scored.paper.fulltext_path else "embedded")
    stem = normalize_title(scored.paper.title)[:80] or scored.paper.source_id
    cache_dir = run_dir / "cache" / "fulltexts"
    pdf_path = download_pdf(scored.paper.pdf_url, cache_dir, stem)
    if pdf_path is None:
        return LoadedFulltext(text="", backend="missing-pdf")
    try:
        loaded = extract_with_mineru(pdf_path, cache_dir, stem)
    except Exception:
        return LoadedFulltext(text="", backend="mineru-exception", path=str(pdf_path))
    if loaded.text.strip():
        return loaded
    if not loaded.path:
        loaded.path = str(pdf_path)
    return loaded


def normalize_fulltext(text: str) -> str:
    normalized = text.replace("\r", "\n")
    normalized = re.sub(r"-\n(?=[a-z])", "", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def canonical_heading(line: str) -> str | None:
    cleaned = re.sub(r"^[#>*\-\s]+", "", line.strip())
    cleaned = re.sub(r"^(?:\d+(?:\.\d+)*|[IVXLCM]+)[.)]?\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" :.-").lower()
    if not cleaned or len(cleaned) > 80:
        return None
    for key, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if cleaned == alias or cleaned.startswith(alias + " "):
                return key
    return None


def collect_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_ALIASES}
    current: str | None = None
    normalized = normalize_fulltext(text)
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = canonical_heading(line)
        if heading is not None:
            current = heading
            continue
        if current is None:
            continue
        sections[current].append(line)
    merged = {key: " ".join(value).strip() for key, value in sections.items()}
    if any(section_is_usable(value, minimum_chars=20) for value in merged.values()):
        return merged

    inline_map = {
        "introduction": "introduction",
        "background": "introduction",
        "method": "method",
        "methods": "method",
        "approach": "method",
        "methodology": "method",
        "training": "training",
        "optimization": "training",
        "experiments": "experiments",
        "experiment": "experiments",
        "evaluation": "experiments",
        "results": "experiments",
        "conclusion": "conclusion",
        "discussion": "conclusion",
    }
    pattern = re.compile(r"(?:(?<=^)|(?<=[\n.!?]))\s*(Introduction|Background|Method|Methods|Approach|Methodology|Training|Optimization|Experiments|Experiment|Evaluation|Results|Conclusion|Discussion)\b", flags=re.IGNORECASE)
    matches = list(pattern.finditer(normalized))
    for idx, match in enumerate(matches):
        key = inline_map.get(match.group(1).lower())
        if not key:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
        content = normalized[start:end].strip()
        if content:
            sections[key].append(content)
    return {key: " ".join(value).strip() for key, value in sections.items()}


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not normalized:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]


def find_url(text: str, token: str) -> str:
    match = re.search(rf"https?://[^\s)\]>]*{re.escape(token)}[^\s)\]>]*", text, flags=re.IGNORECASE)
    return match.group(0).rstrip('.,);]') if match else ""


def section_is_usable(text: str, *, minimum_words: int = 6, minimum_chars: int = 40) -> bool:
    return len(text) >= minimum_chars and len(text.split()) >= minimum_words


def pick_sentences(text: str, keywords: list[str], *, limit: int = 2, fallback_limit: int = 1) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    sentences = split_sentences(text)
    for sentence in sentences:
        lower = sentence.lower()
        if keywords and not any(re.search(keyword_pattern(keyword), lower) for keyword in keywords):
            continue
        key = normalize_title(sentence)[:160]
        if key in seen:
            continue
        seen.add(key)
        selected.append(sentence)
        if len(selected) >= limit:
            return selected
    if selected:
        return selected
    for sentence in sentences:
        if len(sentence) < 40:
            continue
        key = normalize_title(sentence)[:160]
        if key in seen:
            continue
        seen.add(key)
        selected.append(sentence)
        if len(selected) >= fallback_limit:
            break
    return selected


def match_descriptions(text: str, patterns: list[tuple[str, str]], *, limit: int = 4) -> list[str]:
    lower = text.lower()
    out: list[str] = []
    for pattern, description in patterns:
        if re.search(pattern, lower, flags=re.IGNORECASE) and description not in out:
            out.append(description)
        if len(out) >= limit:
            break
    return out


def format_term_list(items: list[str], *, fallback: str) -> str:
    return "，".join(items) if items else fallback


def safe_excerpt(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def infer_problem_cn(scored: ScoredCandidate, intro: str, method: str) -> str:
    hay = f"{scored.paper.title} {intro} {method}".lower()
    if scored.primary_topic == "docking":
        return "更稳地生成/排序 protein-ligand pose，并把 binding affinity 或 confidence 真正纳入决策"
    if scored.primary_topic == "protein":
        if "design" in hay or "generation" in hay:
            return "把蛋白序列设计/生成做得更可控，而不是只会堆表征"
        return "把蛋白表征学到下游任务真正能用，而不是停在漂亮 embedding"
    if scored.primary_topic == "small-molecule":
        if "conformation" in hay:
            return "把小分子构象生成做得更稳定、更贴近下游发现流程"
        return "把小分子表征、生成或性质预测做得更可泛化"
    return "把 ML/DL 方法真正压到 AI4S 问题上，而不是泛泛讲生物应用故事"


def build_summary_cn(scored: ScoredCandidate, intro: str, method: str, experiments: str) -> str:
    method_desc = format_term_list(match_descriptions(method, ARCHITECTURE_HINTS, limit=3), fallback=method_cn(scored.method_tags))
    problem_desc = infer_problem_cn(scored, intro, method)
    exp_desc = format_term_list(match_descriptions(experiments, RESULT_HINTS, limit=3), fallback="至少把实验主结果和对比做出来了")
    return (
        f"这篇论文盯的是 **{topic_cn(scored.primary_topic)}**，核心问题是 **{problem_desc}**。"
        f" 从全文看，它的技术主线可以概括成 **{method_desc}**；实验部分至少给出了 **{exp_desc}**，"
        f"所以这篇不是只靠 abstract 撑门面的轻飘稿。"
    )


def build_roast_cn(score: int, *, experiments: str, training: str, code_url: str, method_tags: list[str]) -> tuple[str, str]:
    exp_signals = match_descriptions(experiments, RESULT_HINTS, limit=6)
    train_signals = match_descriptions(training, TRAINING_HINTS + LOSS_HINTS, limit=6)
    method_label = method_cn(method_tags)
    has_ablation = any("ablation" in item for item in exp_signals)
    has_open_code = code_url != "暂无"
    if score >= 8:
        roast = (
            f"这篇至少不是那种把 **{method_label}** 贴到分子任务上就想糊弄过关的稿。"
            f" 方法、训练和实验三条线基本都能对上，{'还给了代码，复现友好。' if has_open_code else '唯一遗憾是没把复现门槛继续往下压。'}"
        )
        worth = "值得细读，优先级可以放在今天前排。"
    elif score >= 6:
        roast = (
            f"方向是对的，**{method_label}** 也不是瞎蹭热点，但硬度还没到拍桌子级别。"
            f" {'有 ablation，说明作者至少知道该怎么自证。' if has_ablation else '实验自证还不够狠，读的时候别被漂亮标题骗了。'}"
        )
        worth = "可以细读，但更适合带着具体问题去看。"
    else:
        roast = (
            f"相关性还在，但更像‘题目很会起，内容没那么硬’。"
            f" {'训练细节写得还行，' if train_signals else '训练策略交代得很省，'}{'实验也不算扎实。' if len(exp_signals) < 2 else '但实验至少没完全摆烂。'}"
        )
        worth = "先扫实验表和方法图，再决定要不要投入全文时间。"
    return roast, worth


def build_architecture_cn(scored: ScoredCandidate, method: str) -> list[str]:
    architecture = format_term_list(match_descriptions(method, ARCHITECTURE_HINTS, limit=4), fallback=f"主要靠 {method_cn(scored.method_tags)} 信号支撑")
    modules = format_term_list(match_descriptions(method, MODULE_HINTS, limit=4), fallback="模块细节写得不算特别慷慨，但能看出不是纯概念稿")
    evidence = pick_sentences(method, ["framework", "model", "encoder", "decoder", "diffusion", "flow matching", "graph", "confidence", "rank", "affinity"], limit=1)
    return [
        f"整体框架：全文方法段落显示它主要是 **{architecture}**，不是单纯在旧 baseline 上补个小 head。",
        f"关键模块：能直接看出来的模块抓手包括 **{modules}**。",
        f"原文方法抓手：{safe_excerpt(evidence[0]) if evidence else '方法段没有给出特别清楚的一句总括，但主线仍可从段落组织中看出来。'}",
    ]


def build_innovation_cn(scored: ScoredCandidate, intro: str, method: str) -> list[str]:
    innovations = format_term_list(match_descriptions(intro + " " + method, INNOVATION_HINTS, limit=4), fallback="创新点更像组合拳，而不是一个单独神仙模块")
    problem_desc = infer_problem_cn(scored, intro, method)
    evidence = pick_sentences(intro + " " + method, ["we propose", "novel", "first", "unified", "framework", "end-to-end"], limit=1)
    return [
        f"核心创新：它真正想卖的是 **{innovations}**，而不是只换个 backbone 名字。",
        f"它试图解决的问题是：**{problem_desc}**。如果这个问题命中你当前项目，它就有继续细读的价值。",
        f"原文创新抓手：{safe_excerpt(evidence[0]) if evidence else '文中没有非常直给的一句 novelty slogan，但整体动机和方法对位关系是清楚的。'}",
    ]


def build_training_cn(method: str, training: str, experiments: str) -> list[str]:
    combined = " ".join([method, training, experiments])
    training_desc = format_term_list(match_descriptions(combined, TRAINING_HINTS, limit=4), fallback="训练范式没有完全展开，说明写法更偏方法 paper 而不是 recipe paper")
    losses = format_term_list(match_descriptions(combined, LOSS_HINTS, limit=4), fallback="损失函数没有被充分展开，读原文时需要重点盯 objective 定义")
    evidence = pick_sentences(combined, ["training", "pretrain", "post training", "objective", "loss", "contrastive", "fine-tune", "optimization"], limit=1)
    return [
        f"训练范式：从全文能确认的训练策略包括 **{training_desc}**。",
        f"目标/损失：能抓到的 objective 信号主要是 **{losses}**。",
        f"原文训练抓手：{safe_excerpt(evidence[0]) if evidence else '训练细节没写得特别豪华，这会直接影响复现难度判断。'}",
    ]


def build_experiments_cn(experiments: str, code_url: str, worth_reading: str) -> list[str]:
    datasets = format_term_list(match_descriptions(experiments, DATASET_HINTS, limit=5), fallback="数据集名称没被稳定抽出，建议读原文实验设置表")
    results = format_term_list(match_descriptions(experiments, RESULT_HINTS, limit=5), fallback="实验部分至少在讲基准对比，但量化结果抓手还不够丰富")
    evidence = pick_sentences(experiments, ["benchmark", "dataset", "ablation", "outperform", "top-1", "auc", "rmse", "mae", "success"], limit=1)
    reproducibility = "给了代码，复现门槛相对低。" if code_url != "暂无" else "没给代码，复现成本会显著提高。"
    return [
        f"数据集 / 基准：全文实验段明确提到 **{datasets}**。",
        f"结果与对比：能直接抓到的结果信号包括 **{results}**。",
        f"实验抓手：{safe_excerpt(evidence[0]) if evidence else '实验段缺少一句非常抓人的总括，需要回到原文表格细看。'}",
        f"开源与复现：{reproducibility} 是否值得细读：{worth_reading}",
    ]


def clamp_score(value: int) -> int:
    return max(1, min(10, value))


def topic_cn(primary_topic: str) -> str:
    return TOPIC_DISPLAY.get(primary_topic, "AI4S 交叉")


def method_cn(method_tags: list[str]) -> str:
    if not method_tags:
        return "方法信号不够强"
    mapping = {
        "diffusion": "Diffusion",
        "flow-matching": "Flow Matching",
        "representation": "Representation/Post-Training",
    }
    return " / ".join(mapping.get(tag, tag) for tag in method_tags)


def review_candidate(scored: ScoredCandidate, loaded: LoadedFulltext | str, *, index: int) -> ReviewedPaper | None:
    if isinstance(loaded, str):
        loaded = LoadedFulltext(text=loaded, backend="legacy")
    fulltext = loaded.text
    if not fulltext.strip():
        return None
    sections = collect_sections(fulltext)
    intro = sections.get("introduction", "")
    method = sections.get("method", "")
    training = sections.get("training", "") or method
    experiments = sections.get("experiments", "")
    conclusion = sections.get("conclusion", "")
    if not all([
        section_is_usable(intro),
        section_is_usable(method),
        section_is_usable(experiments),
        section_is_usable(conclusion, minimum_words=5, minimum_chars=20),
    ]):
        return None

    code_url = scored.paper.code_url or find_url(fulltext + " " + scored.paper.abstract, "github.com") or "暂无"
    demo_url = scored.paper.demo_url or find_url(fulltext + " " + scored.paper.abstract, "github.io") or "暂无"

    novelty_bonus = min(2, max(1, len(match_descriptions(intro + " " + method, INNOVATION_HINTS, limit=4)) // 2 + 1))
    experiment_bonus = min(2, max(1, len(match_descriptions(experiments, RESULT_HINTS, limit=6)) // 2))
    training_bonus = 1 if match_descriptions(training + " " + method, TRAINING_HINTS + LOSS_HINTS, limit=3) else 0
    code_bonus = 1 if code_url != "暂无" else 0
    venue_bonus = 1 if scored.paper.venue.lower() in PREFERRED_HISTORY_VENUES else 0
    score = clamp_score(3 + scored.relevance_score // 2 + novelty_bonus + experiment_bonus + training_bonus + code_bonus + venue_bonus)

    roast_cn, worth = build_roast_cn(score, experiments=experiments, training=training, code_url=code_url, method_tags=scored.method_tags)
    summary_cn = build_summary_cn(scored, intro, method, experiments)
    architecture_cn = build_architecture_cn(scored, method)
    innovation_cn = build_innovation_cn(scored, intro, method)
    training_cn = build_training_cn(method, training, experiments)
    experiments_cn = build_experiments_cn(experiments, code_url, worth)
    score_reason = (
        f"相关性={scored.relevance_score}/10；创新信号加分={novelty_bonus}；实验信号加分={experiment_bonus}；"
        f"训练细节加分={training_bonus}；开源加分={code_bonus}。"
    )
    return ReviewedPaper(
        index=index,
        source_type=scored.paper.source_type,
        source=scored.paper.source,
        source_id=scored.paper.source_id,
        title=scored.paper.title,
        authors=scored.paper.authors,
        venue=scored.paper.venue,
        published_date=scored.paper.published_date,
        url=scored.paper.url,
        pdf_url=scored.paper.pdf_url or "暂无",
        code_url=code_url,
        demo_url=demo_url,
        primary_topic=scored.primary_topic,
        topic_tags=scored.topic_tags,
        method_tags=scored.method_tags,
        relevance_score=scored.relevance_score,
        score=score,
        score_reason=score_reason,
        worth_reading=worth,
        summary_cn=summary_cn,
        roast_cn=roast_cn,
        architecture_cn=architecture_cn,
        innovation_cn=innovation_cn,
        training_cn=training_cn,
        experiments_cn=experiments_cn,
        fulltext_status="ok",
        fulltext_backend=loaded.backend,
        source_label=SOURCE_TYPE_DISPLAY.get(scored.paper.source_type, scored.paper.source_type),
        evidence={
            "introduction": safe_excerpt(intro, 500),
            "method": safe_excerpt(method, 500),
            "training": safe_excerpt(training, 500),
            "experiments": safe_excerpt(experiments, 500),
            "conclusion": safe_excerpt(conclusion, 500),
        },
    )


def markdown_link(label: str, url: str) -> str:
    if not url or url == "暂无":
        return "暂无"
    return f"[{label}]({url})"


def render_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_review_markdown(reviewed: ReviewedPaper) -> str:
    direction = topic_cn(reviewed.primary_topic)
    method_label = method_cn(reviewed.method_tags)
    authors = ", ".join(reviewed.authors) if reviewed.authors else "暂无"
    lines = [
        f"## [{reviewed.index}] {reviewed.title}",
        "",
        "| 字段 | 内容 |",
        "| --- | --- |",
        f"| 来源类型 | {reviewed.source_label} |",
        f"| Source / Venue | {reviewed.source} / {reviewed.venue} |",
        f"| 方向 | {direction} |",
        f"| 方法标签 | {method_label} |",
        f"| 作者 | {authors} |",
        f"| 发布日期 | {reviewed.published_date} |",
        f"| 论文链接 | {markdown_link('Paper', reviewed.url)} |",
        f"| PDF 链接 | {markdown_link('PDF', reviewed.pdf_url)} |",
        f"| 代码链接 | {markdown_link('Code', reviewed.code_url)} |",
        f"| Demo 链接 | {markdown_link('Demo', reviewed.demo_url)} |",
        f"| 全文解析 | {reviewed.fulltext_backend} |",
        "",
        "### 📌 简介",
        reviewed.summary_cn,
        "",
        "### ☠️ 毒舌点评",
        reviewed.roast_cn,
        "",
        "### 🔧 技术方案",
        "",
        "**方法主线**",
        render_bullets(reviewed.architecture_cn),
        "",
        "**核心创新**",
        render_bullets(reviewed.innovation_cn),
        "",
        "**训练策略**",
        render_bullets(reviewed.training_cn),
        "",
        "### 📊 实验结果",
        "",
        "**实验拆解**",
        render_bullets(reviewed.experiments_cn),
        "",
        f"### ⭐ 评分: {reviewed.score}/10",
        f"理由: {reviewed.score_reason}",
        "",
        "---",
    ]
    return "\n".join(lines).strip() + "\n"


def render_report(date_str: str, reviewed: list[ReviewedPaper]) -> str:
    total = len(reviewed)
    today_count = sum(1 for item in reviewed if item.source_type == "today")
    history_count = sum(1 for item in reviewed if item.source_type == "history")
    lines = [
        f"# {date_str} AI4S 论文速递",
        "",
        f"**共收录**: {total} 篇 | **当天新论文**: {today_count} 篇 | **历史优质论文**: {history_count} 篇",
        "",
        "> 只保留通过全文门槛的论文：必须能从全文里抓到 introduction / method / experiments / conclusion，才能正式进日报和打分。",
        "",
        "## 今日总览",
        "",
        "| 序号 | 标题 | 来源 | 方向 | 方法 | 评分 | 阅读建议 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in sorted(reviewed, key=lambda x: (0 if x.source_type == "today" else 1, -x.score, -x.relevance_score, x.title.lower())):
        lines.append(
            f"| {item.index} | {item.title} | {item.source_label} | {topic_cn(item.primary_topic)} | {method_cn(item.method_tags)} | {item.score}/10 | {item.worth_reading} |"
        )
    lines.extend([
        "",
        "## 阅读说明",
        "",
        "- 这不是全量列表，而是按相关性和全文可读性筛过的一版。",
        "- 评分是为了帮你排阅读顺序，不是假装存在客观真理。",
        "- 技术方案 / 训练策略 / 实验结果都尽量从全文抓证据，而不是只抄 abstract。",
    ])
    for topic in ["protein", "small-molecule", "docking", "other-ai4s-relevant"]:
        bucket = [item for item in reviewed if item.primary_topic == topic]
        if not bucket:
            continue
        lines.extend(["", f"## {topic_cn(topic)}（{len(bucket)} 篇）", ""])
        for item in sorted(bucket, key=lambda x: (x.score, x.relevance_score), reverse=True):
            lines.append(render_review_markdown(item).rstrip())
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def publish_to_feishu(run_dir: Path, report_text: str, *, skip: bool, require: bool) -> dict[str, Any]:
    status = {
        "required": require,
        "skipped": skip,
        "status": "skipped" if skip else "pending",
        "doc_url": "",
        "doc_token": "",
        "error": "",
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
    }
    if skip:
        return status
    try:
        title = f"{os.environ.get('FEISHU_TITLE_PREFIX', 'AI4S 论文速递')} {run_dir.name}"
        doc = os.environ.get("FEISHU_DOC", "")
        base_cmd = ["lark-cli", "docs"]
        if doc:
            cmd = base_cmd + ["+update", "--doc", doc, "--mode", "overwrite", "--markdown", report_text]
        else:
            cmd = base_cmd + ["+create", "--title", title, "--markdown", report_text]
            for env_name, flag in [
                ("FEISHU_FOLDER_TOKEN", "--folder-token"),
                ("FEISHU_WIKI_NODE", "--wiki-node"),
                ("FEISHU_WIKI_SPACE", "--wiki-space"),
            ]:
                value = os.environ.get(env_name)
                if value:
                    cmd.extend([flag, value])
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SourceFetchError((proc.stdout or proc.stderr).strip() or f"lark-cli exited with {proc.returncode}")
        status["status"] = "ok"
        try:
            data = json.loads(proc.stdout or "{}")
            status["doc_url"] = data.get("doc_url", "") or data.get("data", {}).get("doc_url", "")
            status["doc_token"] = data.get("doc_id", "") or data.get("data", {}).get("doc_id", "")
        except Exception:
            pass
        if doc and not status["doc_token"]:
            status["doc_token"] = doc
    except Exception as exc:
        status["status"] = "failed"
        status["error"] = str(exc)
    return status


def build_extraction_manifest(selected: list[ScoredCandidate], loaded_map: dict[str, LoadedFulltext]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for item in selected:
        loaded = loaded_map.get(item.paper.source_id, LoadedFulltext(text="", backend="missing"))
        manifest.append({
            "source_id": item.paper.source_id,
            "title": item.paper.title,
            "source_type": item.paper.source_type,
            "source": item.paper.source,
            "venue": item.paper.venue,
            "published_date": item.paper.published_date,
            "url": item.paper.url,
            "pdf_url": item.paper.pdf_url,
            "authors": item.paper.authors,
            "primary_topic": item.primary_topic,
            "topic_tags": item.topic_tags,
            "method_tags": item.method_tags,
            "relevance_score": item.relevance_score,
            "relevance_reason": item.relevance_reason,
            "fulltext_backend": loaded.backend,
            "pdf_path": loaded.path,
            "markdown_path": loaded.markdown_path,
            "artifact_dir": loaded.artifact_dir,
            "image_paths": loaded.image_paths or [],
            "text_preview": safe_excerpt(loaded.text, 300),
        })
    return manifest


def write_outputs(run_dir: Path, selected: list[ScoredCandidate], reviewed: list[ReviewedPaper], report_text: str, loaded_map: dict[str, LoadedFulltext]) -> None:
    ensure_dir(run_dir)
    ensure_dir(run_dir / "reviewed")
    write_json(run_dir / "selected.json", [
        {
            **asdict(item.paper),
            "relevance_score": item.relevance_score,
            "primary_topic": item.primary_topic,
            "topic_tags": item.topic_tags,
            "method_tags": item.method_tags,
            "relevance_reason": item.relevance_reason,
        }
        for item in selected
    ])
    write_json(run_dir / "extraction_manifest.json", build_extraction_manifest(selected, loaded_map))
    write_json(run_dir / "reviewed.json", [asdict(item) for item in reviewed])
    for item in reviewed:
        stem = f"{item.index:02d}_{normalize_title(item.title)[:60] or item.source_id}"
        (run_dir / "reviewed" / f"{stem}.md").write_text(render_review_markdown(item), encoding="utf-8")
    (run_dir / "report.md").write_text(report_text, encoding="utf-8")


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_date = resolve_date(args.date)
    run_dir = Path(args.output_root) / target_date.isoformat()
    ensure_dir(run_dir)

    if args.dry_run:
        if not args.fixtures:
            raise SystemExit("--dry-run requires --fixtures")
        fixture_dir = Path(args.fixtures)
        today_candidates = load_candidates_from_json(fixture_dir / "today_candidates.json")
        history_candidates = load_candidates_from_json(fixture_dir / "history_candidates.json")
        fixture_base: Path | None = fixture_dir
    else:
        raw_dir = ensure_dir(run_dir / "raw" / "today")
        today_candidates = fetch_today_arxiv_candidates(target_date, raw_dir)
        history_candidates = load_candidates_from_json(Path(args.history_pool))
        fixture_base = Path(args.history_pool).parent

    today_candidates = filter_real_candidates(today_candidates)
    history_candidates = filter_real_candidates(history_candidates)
    today_candidates = deduplicate_candidates(today_candidates)
    history_candidates = deduplicate_candidates(history_candidates)
    scored_today = [score_candidate(item) for item in today_candidates]
    if not args.dry_run and sum(1 for item in scored_today if item.relevance_score >= 5 and item.primary_topic != "other-ai4s-relevant") < args.today_min:
        supplemental = fetch_keyword_today_candidates(target_date, raw_dir)
        today_candidates = deduplicate_candidates(today_candidates + supplemental)
        scored_today = [score_candidate(item) for item in today_candidates]
    scored_history = [score_candidate(item) for item in history_candidates]
    selected = select_final_candidates(scored_today, scored_history, max_total=args.max_total, today_min=args.today_min, today_max=args.today_max)

    reviewed: list[ReviewedPaper] = []
    loaded_map: dict[str, LoadedFulltext] = {}
    for index, scored in enumerate(selected, start=1):
        loaded = load_fulltext(scored, run_dir=run_dir, base_dir=fixture_base, backend_preference=args.fulltext_backend)
        loaded_map[scored.paper.source_id] = loaded
        if args.extract_only:
            continue
        paper = review_candidate(scored, loaded, index=index)
        if paper is not None:
            reviewed.append(paper)

    report_text = render_report(target_date.isoformat(), reviewed) if reviewed else ""
    write_outputs(run_dir, selected, reviewed, report_text, loaded_map)
    publish_status = publish_to_feishu(run_dir, report_text, skip=args.skip_feishu or args.dry_run or args.extract_only or not reviewed, require=args.require_feishu and not args.extract_only)
    write_json(run_dir / "publish.json", publish_status)

    if args.extract_only:
        local_ok = all((run_dir / name).exists() for name in ["selected.json", "extraction_manifest.json", "publish.json"])
        return 0 if selected and local_ok else 1

    local_ok = all((run_dir / name).exists() for name in ["selected.json", "extraction_manifest.json", "reviewed.json", "report.md", "publish.json"])
    if not selected or not reviewed or not local_ok:
        return 1
    if args.require_feishu and publish_status["status"] != "ok":
        return 1
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
