"""Run Alembic migrations programmatically.

This exists because the `alembic` console script is not on PATH in
Railpack/mise runtime, and `python -m alembic` fails (no __main__.py).
"""
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    """Apply all pending migrations to head."""
    project_root = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(project_root / "alembic.ini")), "head")


if __name__ == "__main__":
    main()