"""Smoke test: can the app package load (run from repo root or any cwd)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from main import app  # noqa: E402

print("OK", app.title)
