"""Антиабуз триалов: правило «кто абузер на одном устройстве» и проверка при подключении.

До 2026-10-03: проверялись только группы 3+ аккаунтов раз в 12 часов, группа целиком
пропускалась, если среди аккаунтов с Telegram он был один (аккаунты email/Google/VK
прятались за ним), и наказывался в том числе первый, законный аккаунт.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.external.remnawave_api import UserStatus
from app.services.trial_abuse_service import TrialAbuseService


NOW = datetime.now(UTC).replace(microsecond=0)  # реальное время: сервис сам читает часы
HWID = 'ABCDEF0123456789'


def _panel(uid, *, days_ago, tg=None, status=UserStatus.ACTIVE, expires_in=timedelta(days=1)):
    return SimpleNamespace(
        id=uid,
        created_at=NOW - timedelta(days=days_ago),
        telegram_id=tg,
        short_uuid=f'short{uid}',
        status=status,
        expire_at=NOW + expires_in,
        username=f'u{uid}',
    )


def _index(*records):
    """records: (bot_user_id, panel_ids, tg, paid)."""
    index = {'by_id': {}, 'by_short': {}, 'by_tg': {}, 'paid_panel_ids': set(), 'records': {}}
    for bot_user_id, panel_ids, tg, paid in records:
        record = {
            'bot_user_id': bot_user_id,
            'telegram_id': tg,
            'panel_ids': set(panel_ids),
            'shorts': set(),
            'paid_ever': paid,
            'paid_active': paid,
            'trial_count': 1,
        }
        index['records'][bot_user_id] = record
        for panel_id in panel_ids:
            index['by_id'][panel_id] = record
            if paid:
                index['paid_panel_ids'].add(panel_id)
        if tg:
            index['by_tg'][tg] = record
    return index


def _abusers(users, index):
    svc = TrialAbuseService()
    by_id = {u.id: u for u in users}
    return svc._abusers_in_hwid_group(HWID, set(by_id), by_id, index, NOW)


def test_second_account_on_a_device_is_the_abuser_not_the_first():
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=222)]
    index = _index((10, [1], 111, False), (20, [2], 222, False))

    assert set(_abusers(users, index)) == {2}


def test_two_accounts_are_enough():
    # Раньше группы из 2 аккаунтов не проверялись вовсе (порог 3).
    assert TrialAbuseService().get_min_accounts() == 2


def test_same_bot_user_is_one_person():
    # Две подписки мульти-тарифа одного пользователя бота — два аккаунта панели.
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=111)]
    index = _index((10, [1, 2], 111, False))

    assert _abusers(users, index) == {}


def test_account_without_telegram_no_longer_hides_behind_one_telegram():
    # Telegram-аккаунт + аккаунт с Google/VK на том же устройстве: раньше «один
    # Telegram в группе» пропускал всю группу.
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=None)]
    index = _index((10, [1], 111, False), (20, [2], None, False))

    assert set(_abusers(users, index)) == {2}


def test_paid_and_expired_accounts_are_never_punished():
    users = [
        _panel(1, days_ago=30, tg=111),
        _panel(2, days_ago=5, tg=222),
        _panel(3, days_ago=1, tg=333, expires_in=timedelta(hours=-1)),
    ]
    index = _index((10, [1], 111, False), (20, [2], 222, True), (30, [3], 333, False))

    assert _abusers(users, index) == {}


def test_unknown_accounts_are_not_touched():
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=222)]
    index = _index((10, [1], 111, False))  # аккаунт 2 боту не известен

    assert _abusers(users, index) == {}


# ==================== проверка при подключении устройства ====================


def _realtime_service(monkeypatch, users, index, *, has_trial=True):
    svc = TrialAbuseService()
    svc.bot = MagicMock()
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_ENABLED', True)
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_NOTIFY', False)
    monkeypatch.setattr(svc, '_find_bot_trials', AsyncMock(return_value=[object()] if has_trial else []))
    monkeypatch.setattr(svc, '_load_bot_index', AsyncMock(return_value=index))
    monkeypatch.setattr(svc, '_apply_action', AsyncMock(return_value=(True, 'expired')))
    monkeypatch.setattr(svc, '_notify_admin', AsyncMock())

    api = MagicMock()
    api.get_hwid_devices_by_hwid = AsyncMock(return_value=[{'hwid': HWID, 'userId': u.id} for u in users])
    by_id = {u.id: u for u in users}
    api.get_user_by_id = AsyncMock(side_effect=lambda uid: by_id.get(uid))
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=api)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        'app.services.trial_abuse_service.remnawave_service', SimpleNamespace(get_api_client=lambda: client)
    )
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=MagicMock())
    session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr('app.services.trial_abuse_service.AsyncSessionLocal', lambda: session)
    return svc


async def test_new_device_of_a_second_account_punishes_both_accounts(monkeypatch):
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=0.01, tg=222)]
    svc = _realtime_service(monkeypatch, users, _index((10, [1], 111, False), (20, [2], 222, False)))

    assert await svc.check_new_device(2, HWID) is True
    assert {call.args[1].id for call in svc._apply_action.await_args_list} == {1, 2}  # и первый тоже
    assert svc._punished == {1, 2}


async def test_paid_first_account_keeps_its_access_and_only_the_newcomer_is_punished(monkeypatch):
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=0.01, tg=222)]
    svc = _realtime_service(monkeypatch, users, _index((10, [1], 111, True), (20, [2], 222, False)))

    assert await svc.check_new_device(2, HWID) is True
    assert {call.args[1].id for call in svc._apply_action.await_args_list} == {2}


async def test_whole_group_punishment_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_PUNISH_WHOLE_GROUP', False, raising=False)
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=0.01, tg=222)]
    svc = _realtime_service(monkeypatch, users, _index((10, [1], 111, False), (20, [2], 222, False)))

    assert await svc.check_new_device(2, HWID) is True
    assert {call.args[1].id for call in svc._apply_action.await_args_list} == {2}


async def test_whitelisted_account_is_skipped_but_the_other_one_is_punished(monkeypatch):
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_EXCLUDE_TELEGRAM_IDS', '111', raising=False)
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=0.01, tg=222)]
    svc = _realtime_service(monkeypatch, users, _index((10, [1], 111, False), (20, [2], 222, False)))

    assert await svc.check_new_device(2, HWID) is True
    assert {call.args[1].id for call in svc._apply_action.await_args_list} == {2}


async def test_owner_connecting_again_catches_the_whole_group_too(monkeypatch):
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=222)]
    svc = _realtime_service(monkeypatch, users, _index((10, [1], 111, False), (20, [2], 222, False)))

    assert await svc.check_new_device(1, HWID) is True
    assert {call.args[1].id for call in svc._apply_action.await_args_list} == {1, 2}


async def test_lone_owner_is_never_punished(monkeypatch):
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=222, status=UserStatus.EXPIRED)]
    svc = _realtime_service(monkeypatch, users, _index((10, [1], 111, False), (20, [2], 222, False)))

    assert await svc.check_new_device(1, HWID) is False  # второй аккаунт уже истёк — нарушителей нет
    svc._apply_action.assert_not_awaited()


async def test_non_trial_accounts_skip_the_panel_lookup(monkeypatch):
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=222)]
    svc = _realtime_service(monkeypatch, users, _index(), has_trial=False)

    assert await svc.check_new_device(2, HWID) is False
    svc._load_bot_index.assert_not_awaited()


@pytest.mark.parametrize('hwid', ['', 'unknown', 'short'])
def test_bogus_hwid_is_not_checked(monkeypatch, hwid):
    svc = TrialAbuseService()
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_ENABLED', True)
    svc.check_new_device = AsyncMock()

    svc.schedule_device_check(2, hwid)

    svc.check_new_device.assert_not_called()


def test_realtime_switch(monkeypatch):
    svc = TrialAbuseService()
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_ENABLED', True)
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_REALTIME_ENABLED', False)
    svc.check_new_device = AsyncMock()

    svc.schedule_device_check(2, HWID)

    svc.check_new_device.assert_not_called()


async def test_device_webhook_schedules_the_check_and_still_notifies(monkeypatch):
    from app.services import trial_abuse_service as module
    from app.services.remnawave_webhook_service import RemnaWaveWebhookService

    schedule = MagicMock()
    monkeypatch.setattr(module.trial_abuse_service, 'schedule_device_check', schedule)
    webhook = RemnaWaveWebhookService(MagicMock())
    webhook._notify_user = AsyncMock()
    webhook._get_subscription_keyboard = MagicMock(return_value=None)
    subscription = SimpleNamespace(start_date=datetime.now(UTC) - timedelta(minutes=5))

    await webhook._handle_device_added(
        None, SimpleNamespace(id=1), subscription, {'hwidUserDevice': {'userId': 2, 'hwid': HWID}}
    )

    schedule.assert_called_once_with(2, HWID)
    webhook._notify_user.assert_awaited_once()


# ==================== кто это: имена из бота, а не служебные из панели ====================


def _named_index():
    index = _index((10, [1], 111, False), (20, [2], None, False))
    index['records'][10].update(name='Иван Петров', username='ivan_p', email=None)
    index['records'][20].update(name='', username=None, email='farm@example.com')
    return index


def test_who_shows_real_name_username_and_telegram():
    who = TrialAbuseService()._who(_panel(1, days_ago=30, tg=111), _named_index())
    assert who == 'Иван Петров (@ivan_p, tg 111)'


def test_who_for_email_only_account_and_for_unknown_account():
    svc = TrialAbuseService()
    assert svc._who(_panel(2, days_ago=1), _named_index()) == 'farm@example.com'
    assert svc._who(_panel(99, days_ago=1), _named_index()) == 'аккаунт панели 99'


def test_who_html_links_to_the_telegram_profile_and_escapes():
    index = _named_index()
    index['records'][10]['name'] = 'Иван <b>'
    who = TrialAbuseService()._who(_panel(1, days_ago=30, tg=111), index, html_link=True)
    assert who.startswith('<a href="tg://user?id=111">Иван &lt;b&gt;</a>')


def test_reason_names_the_first_account_on_the_device():
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1)]
    reason = _abusers(users, _named_index())[2]
    assert 'первый — Иван Петров (@ivan_p, tg 111)' in reason
    assert 'id=1' not in reason


# ==================== правило группы, защита наград, отчёт ====================


def _targets(users, index, **settings_patch):
    svc = TrialAbuseService()
    by_id = {u.id: u for u in users}
    return svc._group_targets(HWID, set(by_id), by_id, index, NOW)


def test_group_targets_include_the_first_trial_account():
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=222), _panel(3, days_ago=0.5, tg=333)]
    index = _index((10, [1], 111, False), (20, [2], 222, False), (30, [3], 333, False))

    assert set(_targets(users, index)) == {1, 2, 3}


def test_group_targets_leave_a_paid_first_account_alone_and_ignore_clean_groups():
    users = [_panel(1, days_ago=30, tg=111), _panel(2, days_ago=1, tg=222)]
    assert set(_targets(users, _index((10, [1], 111, True), (20, [2], 222, False)))) == {2}
    paid_newcomer = _index((10, [1], 111, False), (20, [2], 222, True))
    assert _targets(users, paid_newcomer) == {}  # платный новичок — не нарушитель, первого трогать не за что


def _many(n, paid_ids=()):
    users = [_panel(i, days_ago=30 - i * 0.1, tg=1000 + i) for i in range(1, n + 1)]
    records = [(i, [i], 1000 + i, i in paid_ids) for i in range(1, n + 1)]
    return users, _index(*records)


def test_big_device_with_a_noticeable_share_of_paid_accounts_is_left_alone():
    users, index = _many(10, paid_ids={1, 2, 3})  # 30% платных: общее устройство, не ферма
    svc = TrialAbuseService()
    by_id = {u.id: u for u in users}
    stats = {}
    from collections import defaultdict

    stats = defaultdict(int)
    assert svc._group_targets(HWID, set(by_id), by_id, index, NOW, stats) == {}
    assert stats['skipped_shared_device'] == 1


def test_big_device_without_paid_accounts_is_still_a_farm():
    users, index = _many(8)
    assert len(_targets(users, index)) == 8


def test_small_group_with_paid_account_keeps_the_old_rule():
    users, index = _many(3, paid_ids={1})  # группа меньше порога: правило прежнее
    assert set(_targets(users, index)) == {2, 3}


def _api_for_guard(monkeypatch, svc, *, my_devices, by_hwid, index):
    api = MagicMock()
    api.get_user_devices = AsyncMock(return_value={'devices': my_devices})
    api.get_hwid_devices_by_hwid = AsyncMock(side_effect=lambda hwid: by_hwid.get(hwid, []))
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=api)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        'app.services.trial_abuse_service.remnawave_service', SimpleNamespace(get_api_client=lambda: client)
    )
    monkeypatch.setattr(svc, '_load_bot_index', AsyncMock(return_value=index))
    return api


async def test_device_shared_with_another_person_is_suspicious(monkeypatch):
    svc = TrialAbuseService()
    index = _index((10, [1], 111, False), (20, [2], 222, False))
    _api_for_guard(
        monkeypatch, svc, my_devices=[{'hwid': HWID}], index=index,
        by_hwid={HWID: [{'hwid': HWID, 'userId': 1}, {'hwid': HWID, 'userId': 2}]},
    )  # fmt: skip
    assert await svc.shares_device_with_other_person(1) is True


async def test_second_account_of_the_same_person_is_not_suspicious(monkeypatch):
    svc = TrialAbuseService()
    index = _index((10, [1, 2], 111, False))  # оба аккаунта панели — один человек бота
    _api_for_guard(
        monkeypatch, svc, my_devices=[{'hwid': HWID}], index=index,
        by_hwid={HWID: [{'hwid': HWID, 'userId': 1}, {'hwid': HWID, 'userId': 2}]},
    )  # fmt: skip
    assert await svc.shares_device_with_other_person(1) is False


async def test_panel_failure_never_blocks_an_honest_reward(monkeypatch):
    svc = TrialAbuseService()
    monkeypatch.setattr(svc, '_load_bot_index', AsyncMock(side_effect=RuntimeError('панель недоступна')))
    assert await svc.shares_device_with_other_person(1) is False


async def test_friend_reward_is_blocked_for_a_shared_device(monkeypatch):
    from app.services import trial_abuse_service as module, trial_quest_service as quest

    guard = AsyncMock(return_value=True)
    monkeypatch.setattr(module.trial_abuse_service, 'shares_device_with_other_person', guard)
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_REWARD_GUARD', True, raising=False)
    user = SimpleNamespace(id=5, remnawave_id=77)
    assert await quest._reward_is_suspicious(user, SimpleNamespace(remnawave_id=None)) is True
    guard.assert_awaited_once_with(77)
    monkeypatch.setattr(settings, 'TRIAL_ABUSE_REWARD_GUARD', False, raising=False)
    assert await quest._reward_is_suspicious(user, SimpleNamespace(remnawave_id=None)) is False


async def test_already_punished_account_gets_no_friend_reward(monkeypatch):
    from app.services import trial_abuse_service as module, trial_quest_service as quest

    monkeypatch.setattr(settings, 'TRIAL_ABUSE_REWARD_GUARD', True, raising=False)
    monkeypatch.setattr(module.trial_abuse_service, '_punished', {77})
    assert (
        await quest._reward_is_suspicious(SimpleNamespace(id=5, remnawave_id=77), SimpleNamespace(remnawave_id=None))
        is True
    )
