from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.application.production_jobs as production_jobs


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (SimpleNamespace(code=429), "429"),
        (SimpleNamespace(code=404), "404"),
        (SimpleNamespace(code="PROVIDER_BAD_REQUEST"), "PROVIDER_BAD_REQUEST"),
        (RuntimeError("provider failed"), "PRODUCTION_ERROR"),
        (SimpleNamespace(code=None, status_code=429), "429"),
    ],
)
def test_normalized_error_code_preserves_provider_code(exception, expected):
    assert production_jobs._normalized_error_code(exception) == expected


def test_error_diagnostics_are_bounded_and_redact_common_secrets():
    message = (
        "request https://api.telegram.org/bot123456:secret-token/sendMessage "
        "Authorization: Bearer abc.def.secret api_key=AIza0123456789abcdefghijk"
    )
    safe = production_jobs._redact_error_text(message)

    assert "secret-token" not in safe
    assert "abc.def.secret" not in safe
    assert "AIza0123456789abcdefghijk" not in safe
    assert "123456:secret-token" not in safe
    assert len(production_jobs._redact_error_text("x" * 5000)) == 1000


@pytest.mark.asyncio
async def test_diagnostic_write_failure_attempts_minimal_terminal_item_update(monkeypatch):
    sessions = []

    class FakeSession:
        def __init__(self, fail_execute):
            self.fail_execute = fail_execute
            self.committed = False
            self.statement = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def execute(self, statement):
            self.statement = statement
            if self.fail_execute:
                raise RuntimeError("database diagnostic write rejected")

        async def commit(self):
            self.committed = True

    def session_factory():
        session = FakeSession(fail_execute=not sessions)
        sessions.append(session)
        return session

    monkeypatch.setattr(production_jobs, "SessionFactory", session_factory)

    await production_jobs._fail_item(
        uuid4(),
        uuid4(),
        SimpleNamespace(code=429, __str__=lambda self: "rate limited"),
    )

    assert len(sessions) == 2
    assert not sessions[0].committed
    assert sessions[1].committed
    assert sessions[1].statement is not None
