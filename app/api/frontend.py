"""Frontend static-serving boundary.

The React application is built independently under frontend/. FastAPI only
serves the compiled presentation shell and keeps the existing legacy HTML
fallback when the production bundle is not present.
"""
from pathlib import Path

from fastapi.responses import FileResponse

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"


def frontend_available() -> bool:
    return FRONTEND_INDEX.is_file()


def frontend_index_response():
    if not frontend_available():
        return None
    return FileResponse(FRONTEND_INDEX)
