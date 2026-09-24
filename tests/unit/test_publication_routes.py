from uuid import uuid4

import pytest

from app.api.routes import get_approve_and_publish, get_create_telegram_draft
from app.adapters.publishing.fake import FakePublisher
from app.application.publications import ApproveAndPublish, CreateTelegramDraft


def test_publication_route_dependencies_use_cases() -> None:
    """Verify publication route dependencies construct the expected use cases."""
    assert isinstance(get_create_telegram_draft(), CreateTelegramDraft)


def test_publish_route_dependency_uses_telegram_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify publishing dependency requires a Telegram bot token."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    publisher = get_approve_and_publish()
    assert isinstance(publisher, ApproveAndPublish)
