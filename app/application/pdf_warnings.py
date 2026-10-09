"""Narrow, concurrency-safe suppression for a known noisy pypdf reader warning."""

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import re
from threading import Lock
from typing import Iterator

_suppress_missing_object_warning: ContextVar[bool] = ContextVar(
    "suppress_pypdf_missing_object_warning", default=False
)
_filter_lock = Lock()
_filter_installed = False
_MISSING_OBJECT_WARNING = re.compile(r"^Object \d+ \d+ not defined\.$")

class _PypdfWarningFilter(logging.Filter):
    """Filter only the known warning while the calling context opts in."""

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            _suppress_missing_object_warning.get()
            and record.name == "pypdf._reader"
            and record.levelno == logging.WARNING
            and _MISSING_OBJECT_WARNING.fullmatch(record.getMessage())
        ):
            return False
        return True

def _install_filter_once() -> None:
    global _filter_installed
    if _filter_installed:
        return
    with _filter_lock:
        if not _filter_installed:
            logging.getLogger("pypdf._reader").addFilter(_PypdfWarningFilter())
            _filter_installed = True

@contextmanager
def quiet_known_pypdf_warnings() -> Iterator[None]:
    """Silence only the repeated undefined-object warning in this context.

    Logger configuration and levels are never changed. ContextVar keeps
    suppression opt-in scoped to the current execution context, including
    context propagated into asyncio.to_thread workers.
    """
    _install_filter_once()
    token = _suppress_missing_object_warning.set(True)
    try:
        yield
    finally:
        _suppress_missing_object_warning.reset(token)
