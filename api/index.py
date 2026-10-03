"""Vercel entrypoint (ADR-0016): the FastAPI app as one Python function; the console is served as static files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api.main import create_app  # noqa: E402  the backend directory must be on the path first

app = create_app()
