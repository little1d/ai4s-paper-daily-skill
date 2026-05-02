#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
IMPL_PATH = REPO_ROOT / "scripts" / "ai4s_paper_daily.py"

SPEC = importlib.util.spec_from_file_location("ai4s_paper_daily_impl", IMPL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load runner implementation from {IMPL_PATH}")

MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

for name, value in vars(MODULE).items():
    if name.startswith("__") and name not in {"__doc__", "__all__"}:
        continue
    globals()[name] = value

if __name__ == "__main__":
    raise SystemExit(MODULE.main())
