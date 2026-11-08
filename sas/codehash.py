"""Hash of the analysis code, for the pre-registration freeze (decisions §1.6).

Covers sas/analysis*.py, scripts/analyze.py and scripts/report.py as the
decision specifies, plus sas/prereg.py, which holds the frozen constants
(k, SESOI, family, exclusion rule) that the analysis reads.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def analysis_files() -> list[Path]:
    files = sorted((ROOT / "sas").glob("analysis*.py")) + [
        ROOT / "sas" / "prereg.py", ROOT / "scripts" / "analyze.py", ROOT / "scripts" / "report.py"]
    return files


def analysis_code_hash() -> str:
    h = hashlib.sha256()
    for f in analysis_files():
        h.update(str(f.relative_to(ROOT)).encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()
