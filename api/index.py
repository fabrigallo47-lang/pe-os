"""Vercel entrypoint — exposes the PE OS FastAPI app (ASGI) on Fluid Compute."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.server import app  # noqa: E402, F401
