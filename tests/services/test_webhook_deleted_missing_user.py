"""user.deleted для пользователя, чью строку уже удалили: без NoResultFound и без обработчика."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import remnawave_webhook_service as mod


async def test_deleted_event_for_already_removed_user_is_skipped(monkeypatch):
    service = mod.RemnaWaveWebhookService.__new__(mod.RemnaWaveWebhookService)
    user = SimpleNamespace(id=30313)
    monkeypatch.setattr(service, '_resolve_user_and_subscription', AsyncMock(return_value=(user, None)))
    monkeypatch.setattr(mod, 'lock_user_for_update_if_exists', AsyncMock(return_value=None))
    handler = AsyncMock()

    assert await service._process_user_event(AsyncMock(), 'user.deleted', {'id': 1}, handler) is False
    handler.assert_not_awaited()
