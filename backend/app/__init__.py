"""Retail Intelligence back end (FastAPI).

Makes the project root importable so the API reuses the same `config`,
`pipelines` and `ml` modules as the command-line scripts.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
