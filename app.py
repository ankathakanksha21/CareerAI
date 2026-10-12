"""Vercel entrypoint: the FastAPI backend from backend/ plus the built React app from
frontend/dist, served from one deployment. Locally, run the backend with uvicorn from
backend/ and the frontend with Vite instead (see docs/ARCHITECTURE.md section 12)."""
import sys
from pathlib import Path

from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))  # backend modules import each other as top-level modules

from main import app  # noqa: E402

DIST = ROOT / "frontend" / "dist"
if DIST.is_dir():
    # Mounted after every /api route is registered, so the API always wins
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
