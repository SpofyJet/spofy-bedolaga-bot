"""Тесты изолированы от боевого окружения и не ходят в Telegram.

30.10.2026 полный прогон pytest, запущенный агентом с боевым ``.env`` в
окружении процесса, отправил фикстуры («Standard Plan» за 300 ₽, «Суточный»
за 10 ₽) в админ-чат как настоящие покупки. Эти проверки не дают такому
повториться: ``conftest`` жёстко подменяет опасные настройки, а сетевой слой
aiogram в тестах поднимает исключение вместо запроса.
"""

import pytest
from conftest import TelegramApiBlockedInTests

from app.bot_factory import create_bot
from app.config import settings
from app.services import guest_purchase_service, subscription_renewal_service


def test_settings_do_not_leak_from_dotenv_or_process_env():
    assert settings.BOT_TOKEN == 'test-token'
    assert settings.ADMIN_NOTIFICATIONS_ENABLED is False
    assert settings.ADMIN_REPORTS_ENABLED is False
    assert not settings.REMNAWAVE_API_URL
    assert not settings.REMNAWAVE_API_KEY
    assert 'localhost/test_db' in (settings.DATABASE_URL or '')


@pytest.mark.asyncio
async def test_real_bot_cannot_reach_telegram():
    # Валидный по формату токен: Bot() собирается, но запрос уйти не должен.
    bot = create_bot(token='123456:TEST-TOKEN')
    try:
        with pytest.raises(TelegramApiBlockedInTests):
            await bot.get_me()
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_renewal_admin_notification_is_swallowed_not_sent(monkeypatch):
    """Даже с включёнными уведомлениями и «боевым» токеном сообщение не уходит."""
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', True)
    monkeypatch.setattr(settings, 'BOT_TOKEN', '123456:TEST-TOKEN')
    seen: list[str] = []

    async def handler(service):
        seen.append('called')
        await service.bot.send_message(chat_id=1, text='fixture')

    await subscription_renewal_service.with_admin_notification_service(handler)
    assert seen == ['called']


@pytest.mark.asyncio
async def test_guest_purchase_admin_notification_is_swallowed_not_sent(monkeypatch):
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', True)
    monkeypatch.setattr(settings, 'BOT_TOKEN', '123456:TEST-TOKEN')

    class _Purchase:
        id = 1
        is_gift = True
        source = 'landing'
        contact_type = 'email'
        contact_value = 'x@example.com'
        period_days = 30
        amount_kopeks = 30000
        payment_method = 'balance'
        campaign_slug = None
        landing_path = '/buy/'
        buyer_user_id = None
        user_id = None
        token = 'x' * 64

    # Не должно ни упасть, ни отправить: исключение сети глотается best-effort.
    await guest_purchase_service._send_admin_notification(_Purchase(), 'Standard Plan')
