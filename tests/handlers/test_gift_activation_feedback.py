"""Подарок: человек видит понятный текст и кнопки, а не сырые <tg-emoji> и тупик.

- Кнопка «Активировать» из уведомления: тексты с <tg-emoji> шли с parse_mode=None
  (пользователь видел теги), после успеха/ошибки не было ни одной кнопки.
- /start GIFT_… с несуществующим/устаревшим кодом молча открывал меню.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User as TgUser

import app.handlers.gift_activation as gift_act_mod
from app.database.crud.landing import generate_purchase_token
from app.database.models import GuestPurchase, GuestPurchaseStatus, User
from app.handlers.start import cmd_start
from app.utils.gift_links import build_bot_gift_claim_link
from tests.fixtures.sqlite_memory import memory_session
from tests.handlers.test_gift_deeplink_activation import (
    _TABLES,
    _make_fsm_context,
    _make_message,
    _seed_tariffs_and_settings,
)


def _callbacks(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row}


def _callback(purchase_id: int, telegram_id: int):
    callback = MagicMock(spec=CallbackQuery)
    callback.data = f'gift_activate:{purchase_id}'
    callback.from_user = TgUser(id=telegram_id, is_bot=False, first_name='Rec')
    callback.message = MagicMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _use_session(monkeypatch, db) -> None:
    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(gift_act_mod, 'AsyncSessionLocal', lambda: _Ctx())


@pytest.mark.asyncio
async def test_callback_success_is_html_with_subscription_and_menu_buttons(monkeypatch):
    async with memory_session(monkeypatch, _TABLES) as db:
        t1, _ = await _seed_tariffs_and_settings(db)
        recipient = User(telegram_id=22222, username='rec', balance_kopeks=0, language='ru')
        db.add(recipient)
        await db.commit()
        await db.refresh(recipient)
        purchase = GuestPurchase(
            token=generate_purchase_token(),
            contact_type='telegram',
            contact_value=str(recipient.telegram_id),
            is_gift=True,
            status=GuestPurchaseStatus.PENDING_ACTIVATION.value,
            tariff_id=t1.id,
            period_days=30,
            amount_kopeks=30000,
            user_id=recipient.id,
        )
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)

        _use_session(monkeypatch, db)
        callback = _callback(purchase.id, recipient.telegram_id)
        with patch('app.services.subscription_service.SubscriptionService.create_remnawave_user', AsyncMock()):
            await gift_act_mod.handle_gift_activate(callback)

    last = callback.message.edit_text.await_args
    assert 'Подарок активирован' in last.args[0]
    assert last.kwargs['parse_mode'] == 'HTML'
    assert _callbacks(last.kwargs['reply_markup']) == {'menu_subscription', 'back_to_menu'}


@pytest.mark.asyncio
async def test_callback_error_is_html_and_not_a_dead_end(monkeypatch):
    async with memory_session(monkeypatch, _TABLES) as db:
        await _seed_tariffs_and_settings(db)
        recipient = User(telegram_id=22222, username='rec', balance_kopeks=0, language='ru')
        db.add(recipient)
        await db.commit()

        _use_session(monkeypatch, db)
        callback = _callback(999_999, recipient.telegram_id)  # такого подарка нет
        await gift_act_mod.handle_gift_activate(callback)

    for call in callback.message.edit_text.await_args_list[1:]:  # первый — «Активируем подарок...»
        assert call.kwargs['parse_mode'] == 'HTML', 'тексты с <tg-emoji> нельзя слать без HTML'
    last = callback.message.edit_text.await_args
    assert 'Подарок не найден' in last.args[0]
    assert 'back_to_menu' in _callbacks(last.kwargs['reply_markup'])


@pytest.mark.asyncio
async def test_unknown_gift_deeplink_says_not_found_instead_of_silent_menu(monkeypatch):
    async with memory_session(monkeypatch, _TABLES) as db:
        await _seed_tariffs_and_settings(db)
        user = User(telegram_id=22222, username='rec', balance_kopeks=0, language='ru')
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Ссылка правильного формата, но такого подарка (уже) нет.
        start_param = build_bot_gift_claim_link(generate_purchase_token(), 'my_bot').split('start=')[1]
        msg = _make_message(f'/start {start_param}', user_id=user.telegram_id, username='rec')
        state = _make_fsm_context(user.telegram_id)
        await cmd_start(msg, state, db, db_user=user)

    answered = [call.args[0] for call in msg.answer.call_args_list if call.args]
    assert any('Подарок не найден' in text for text in answered)
