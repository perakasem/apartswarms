"""Print the analysis-code hash to record in docs/PREREGISTRATION.md.

  uv run scripts/analysis_hash.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sas.codehash import ROOT, analysis_code_hash, analysis_files  # noqa: E402

if __name__ == "__main__":
    for f in analysis_files():
        print(f"  {f.relative_to(ROOT)}")
    print(f"analysis code sha256: {analysis_code_hash()}")
