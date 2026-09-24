"""Run Alembic migrations programmatically.

This exists because the `alembic` console script is not on PATH in
Railpack/mise runtime, and `python -m alembic` fails (no __main__.py).
"""
from alembic.config import Config
from alembic import command


def main() -> None:
    """Apply all pending migrations to head."""
    command.upgrade(Config("alembic.ini"), "head")


if __name__ == "__main__":
    main()