"""Копия Telegram-рассылки письмом тем, у кого нет Telegram.

Проверяем: перевод текста Telegram в письмо, тему, выбор адресатов, случаи,
когда копия не нужна, суточный предел и продолжение очереди из файла.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services import broadcast_email_mirror as mirror_module
from app.services.broadcast_email_mirror import (
    DEFAULT_SUBJECT,
    BroadcastEmailMirror,
    DailyCounter,
    build_email_body,
    pick_mirror_user_ids,
    should_mirror,
    subject_from_telegram_text,
    telegram_html_to_email_html,
)
from app.services.broadcast_service import BroadcastConfig, BroadcastService, _EmailRecipient


# --- текст -------------------------------------------------------------------


def test_tg_emoji_becomes_its_fallback_and_spoiler_plain_text():
    text = (
        '<tg-emoji emoji-id="5440539497383087970">🎁</tg-emoji> Подарок\n'
        '<tg-spoiler>секрет</tg-spoiler> и <span class="tg-spoiler">ещё</span>'
    )
    result = telegram_html_to_email_html(text)
    assert 'tg-emoji' not in result and 'tg-spoiler' not in result and 'span' not in result
    assert result.startswith('🎁 Подарок<br>')
    assert 'секрет и ещё' in result


def test_allowed_tags_kept_rest_stripped_and_escaped():
    text = (
        '<b>Жирный</b> <strong>сильный</strong> <i>к</i> <u>п</u> <s>з</s> <code>x</code>\n'
        '<pre>a\nb</pre><blockquote>цитата</blockquote>'
        '<a href="https://example.org/?a=1&amp;b=2">ссылка</a> <a href="javascript:alert(1)">плохая</a>'
        '<script>alert(1)</script> 5 &lt; 6 <unknown>текст</unknown>'
    )
    result = telegram_html_to_email_html(text)
    for fragment in ('<b>Жирный</b>', '<b>сильный</b>', '<i>к</i>', '<u>п</u>', '<s>з</s>', '<code>x</code>'):
        assert fragment in result
    assert '<pre>a\nb</pre>' in result
    assert '<blockquote>цитата</blockquote>' in result
    assert '<a href="https://example.org/?a=1&amp;b=2">ссылка</a>' in result
    assert 'javascript' not in result and 'плохая' in result
    assert '<script>' not in result
    assert '5 &lt; 6' in result
    assert '<unknown>' not in result and 'текст' in result


def test_unclosed_tags_are_closed():
    assert telegram_html_to_email_html('<b>начало') == '<b>начало</b>'


def test_subject_is_first_non_empty_line_without_tags():
    text = '\n  \n<tg-emoji emoji-id="1">🔥</tg-emoji> <b>Скидка</b> 20% &amp; бонус\nвторая строка'
    assert subject_from_telegram_text(text) == '🔥 Скидка 20% & бонус'


def test_subject_is_cut_to_90_chars_and_has_fallback():
    long_subject = subject_from_telegram_text('а' * 200)
    assert len(long_subject) <= 90 and long_subject.endswith('…')
    assert subject_from_telegram_text('') == DEFAULT_SUBJECT
    assert subject_from_telegram_text('<b> </b>\n') == DEFAULT_SUBJECT
    assert subject_from_telegram_text(None) == DEFAULT_SUBJECT


def test_callback_buttons_become_one_cabinet_link_url_buttons_stay(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', 'https://cab.example.org')
    body = build_email_body(
        'Текст',
        has_callback_buttons=True,
        custom_buttons=[
            {'label': 'Сайт', 'action_type': 'url', 'action_value': 'https://site.example.org'},
            {'label': 'Меню', 'action_type': 'callback', 'action_value': 'menu'},
        ],
    )
    assert body.count('Открыть личный кабинет') == 1
    assert 'href="https://cab.example.org"' in body
    assert 'href="https://site.example.org">Сайт</a>' in body
    assert 'menu' not in body


def test_no_cabinet_link_without_configured_cabinet(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', 'https://example.com/cabinet')
    body = build_email_body('Текст', has_callback_buttons=True)
    assert 'Открыть личный кабинет' not in body


def test_callback_custom_button_alone_gives_cabinet_link(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', 'https://cab.example.org')
    body = build_email_body(
        'Текст', has_callback_buttons=False, custom_buttons=[{'label': 'Меню', 'action_value': 'menu'}]
    )
    assert 'Открыть личный кабинет' in body


# --- адресаты ----------------------------------------------------------------


def _user(user_id, *, telegram_id=None, email='x@example.org', verified=True, status='active', settings_=None):
    return SimpleNamespace(
        id=user_id,
        telegram_id=telegram_id,
        email=email,
        email_verified=verified,
        status=status,
        notification_settings=settings_ or {},
    )


def test_only_users_without_telegram_and_with_verified_email():
    users = [
        _user(5),
        _user(1, telegram_id=111),  # получит в Telegram
        _user(2, email=None),
        _user(3, verified=False),
        _user(4, status='blocked'),
        _user(6, status='deleted'),
        _user(5),  # дубль
    ]
    assert pick_mirror_user_ids(users) == [5, 6]


def test_category_unsubscribe_is_respected():
    users = [_user(1, settings_={'news_enabled': False}), _user(2)]
    assert pick_mirror_user_ids(users, 'news') == [2]
    assert pick_mirror_user_ids(users, 'system') == [1, 2]


# --- когда копия не нужна ----------------------------------------------------


def _config(**kwargs) -> BroadcastConfig:
    base = {'target': 'all', 'message_text': 'Привет', 'selected_buttons': ['balance']}
    base.update(kwargs)
    return BroadcastConfig(**base)


def test_should_mirror_skips_resume_and_personal_sends():
    assert should_mirror(_config(), resume=False)
    assert not should_mirror(_config(), resume=True)
    assert not should_mirror(_config(recipient_ids=[1, 2]), resume=False)
    assert not should_mirror(_config(keyboard_factory=lambda _tid: None), resume=False)


async def _start_broadcast_calls(monkeypatch, config, *, resume=False) -> list[int]:
    service = BroadcastService()
    service.set_bot(object())
    started: list[int] = []

    async def fake_run(*args, **kwargs):
        return None

    async def fake_mirror(broadcast_id, cfg):
        started.append(broadcast_id)
        return 0

    monkeypatch.setattr(service, '_run_broadcast', fake_run)
    monkeypatch.setattr(mirror_module.broadcast_email_mirror, 'start_from_config', fake_mirror)
    await service.start_broadcast(77, config, resume=resume)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return started


async def test_start_broadcast_starts_mirror_for_regular_broadcast(monkeypatch):
    assert await _start_broadcast_calls(monkeypatch, _config()) == [77]


@pytest.mark.parametrize(
    ('config_kwargs', 'resume'),
    [
        ({}, True),
        ({'recipient_ids': [1]}, False),
        ({'keyboard_factory': lambda _tid: None}, False),
    ],
)
async def test_start_broadcast_skips_mirror(monkeypatch, config_kwargs, resume):
    assert await _start_broadcast_calls(monkeypatch, _config(**config_kwargs), resume=resume) == []


async def test_start_broadcast_respects_switch(monkeypatch):
    monkeypatch.setattr(settings, 'BROADCAST_EMAIL_MIRROR_ENABLED', False)
    assert await _start_broadcast_calls(monkeypatch, _config()) == []


# --- очередь, предел, продолжение -------------------------------------------


class _FakeEmailService:
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.sent: list[dict] = []
        self.fail_for = fail_for or set()

    def is_configured(self) -> bool:
        return True

    def send_email(self, **kwargs) -> bool:
        self.sent.append(kwargs)
        return kwargs['to_email'] not in self.fail_for


def _mirror(tmp_path, monkeypatch, email_service, *, limit=300, channel_has_email=False) -> BroadcastEmailMirror:
    mirror = BroadcastEmailMirror(directory=tmp_path)
    mirror.set_email_service(email_service)
    mirror.send_interval = 0
    monkeypatch.setattr(settings, 'BROADCAST_EMAIL_MIRROR_ENABLED', True)
    monkeypatch.setattr(settings, 'BROADCAST_EMAIL_MIRROR_DAILY_LIMIT', limit)
    monkeypatch.setattr(DailyCounter, '_redis', staticmethod(lambda: None))

    async def fake_load(user_ids):
        return {
            uid: _EmailRecipient(email=f'u{uid}@example.org', user_name=f'u{uid}', user_id=uid)
            for uid in user_ids
            if uid != 13  # 13-й отвязал почту
        }

    async def fake_channel(_broadcast_id):
        return channel_has_email

    monkeypatch.setattr(mirror, '_load_recipients', fake_load)
    monkeypatch.setattr(mirror, '_channel_has_email', fake_channel)
    return mirror


async def _wait_tasks(mirror: BroadcastEmailMirror) -> None:
    tasks = list(mirror._tasks.values())
    if tasks:
        await asyncio.gather(*tasks)


@pytest.mark.parametrize('channel_has_email', [True])
async def test_broadcast_with_email_channel_is_not_mirrored(tmp_path, monkeypatch, channel_has_email):
    email = _FakeEmailService()
    mirror = _mirror(tmp_path, monkeypatch, email, channel_has_email=channel_has_email)
    count = await mirror.start(5, user_ids=[1, 2], message_text='Привет')
    assert count == 0
    assert not list(tmp_path.iterdir())
    assert email.sent == []


@pytest.mark.parametrize(('channel_has_email', 'expected'), [(True, 0), (False, 2)])
async def test_start_from_config_checks_channel_before_selecting(tmp_path, monkeypatch, channel_has_email, expected):
    email = _FakeEmailService()
    mirror = _mirror(tmp_path, monkeypatch, email, channel_has_email=channel_has_email)
    selected: list[str] = []

    async def fake_fetch(target, category, audience):
        selected.append(target)
        return [1, 2]

    monkeypatch.setattr(mirror_module, 'fetch_mirror_user_ids', fake_fetch)
    assert await mirror.start_from_config(8, _config()) == expected
    await _wait_tasks(mirror)
    assert selected == ([] if channel_has_email else ['all'])
    assert len(email.sent) == expected


async def test_mirror_sends_to_all_and_cleans_up(tmp_path, monkeypatch):
    email = _FakeEmailService(fail_for={'u3@example.org'})
    mirror = _mirror(tmp_path, monkeypatch, email)
    count = await mirror.start(
        5, user_ids=[1, 2, 3, 13], message_text='<b>Новости</b>\nтекст', has_callback_buttons=True, category='news'
    )
    assert count == 4
    await _wait_tasks(mirror)

    assert [m['to_email'] for m in email.sent] == ['u1@example.org', 'u2@example.org', 'u3@example.org']
    first = email.sent[0]
    assert first['subject'] == 'Новости'
    assert '<b>Новости</b><br>' in first['body_html']
    assert first['unsubscribe_url']  # новости — с отпиской
    assert first['queue_on_failure'] is False
    assert not list(tmp_path.iterdir())  # очередь закрыта, файл удалён


async def test_daily_limit_waits_for_next_day_and_keeps_queue_in_file(tmp_path, monkeypatch):
    email = _FakeEmailService()
    mirror = _mirror(tmp_path, monkeypatch, email, limit=2)
    waits: list[dict] = []

    async def fake_wait(seconds):
        if seconds > 60:  # ждём следующих суток
            waits.append(json.loads((tmp_path / '9.json').read_text(encoding='utf-8')))
            mirror.counter._memory.clear()  # наступили новые сутки

    monkeypatch.setattr(mirror, '_wait', fake_wait)
    await mirror.start(9, user_ids=[1, 2, 3], message_text='Привет')
    await _wait_tasks(mirror)

    assert len(waits) == 1
    assert waits[0]['user_ids'] == [3] and waits[0]['sent'] == 2
    assert 'u1@example.org' not in json.dumps(waits[0])  # в файле только id
    assert [m['to_email'] for m in email.sent] == ['u1@example.org', 'u2@example.org', 'u3@example.org']


async def test_daily_limit_is_shared_between_broadcasts(tmp_path, monkeypatch):
    email = _FakeEmailService()
    mirror = _mirror(tmp_path, monkeypatch, email, limit=3)
    stop = asyncio.Event()

    async def fake_wait(seconds):
        if seconds > 60:
            stop.set()
            raise asyncio.CancelledError

    monkeypatch.setattr(mirror, '_wait', fake_wait)
    await mirror.start(1, user_ids=[1, 2], message_text='a')
    await _wait_tasks(mirror)
    await mirror.start(2, user_ids=[3, 4], message_text='b')
    with pytest.raises(asyncio.CancelledError):
        await _wait_tasks(mirror)

    assert len(email.sent) == 3
    saved = json.loads((tmp_path / '2.json').read_text(encoding='utf-8'))
    assert saved['user_ids'] == [4]


async def test_queue_resumes_from_file_after_restart(tmp_path, monkeypatch):
    email = _FakeEmailService()
    mirror = _mirror(tmp_path, monkeypatch, email)
    state = {
        'broadcast_id': 42,
        'subject': 'Тема',
        'body_html': '<div>Текст</div>',
        'category': 'system',
        'user_ids': [7, 8],
        'attachment_path': None,
        'total': 5,
        'sent': 3,
        'failed': 0,
    }
    (tmp_path / '42.json').write_text(json.dumps(state), encoding='utf-8')

    assert await mirror.resume_pending() == 1
    await _wait_tasks(mirror)

    assert [m['to_email'] for m in email.sent] == ['u7@example.org', 'u8@example.org']
    assert email.sent[0]['subject'] == 'Тема'
    assert email.sent[0]['unsubscribe_url'] is None  # system — без отписки
    assert not (tmp_path / '42.json').exists()


async def test_photo_is_attached(tmp_path, monkeypatch):
    email = _FakeEmailService()
    mirror = _mirror(tmp_path, monkeypatch, email)

    class _Bot:
        async def download(self, file_id, destination):
            destination.write_bytes(b'jpeg-bytes')

    mirror.set_bot(_Bot())
    await mirror.start(3, user_ids=[1], message_text='Фото', media_type='photo', media_file_id='fid')
    await _wait_tasks(mirror)

    assert email.sent[0]['attachments'] == [('photo.jpg', b'jpeg-bytes', 'image/jpeg')]
    assert not list(tmp_path.iterdir())


async def test_photo_download_failure_sends_without_it(tmp_path, monkeypatch):
    email = _FakeEmailService()
    mirror = _mirror(tmp_path, monkeypatch, email)

    class _Bot:
        async def download(self, file_id, destination):
            raise RuntimeError('file is too big')

    mirror.set_bot(_Bot())
    await mirror.start(3, user_ids=[1], message_text='Фото', media_type='photo', media_file_id='fid')
    await _wait_tasks(mirror)

    assert len(email.sent) == 1 and email.sent[0]['attachments'] is None


async def test_failure_streak_returns_people_to_queue(tmp_path, monkeypatch):
    email = _FakeEmailService(fail_for={f'u{i}@example.org' for i in range(1, 11)})
    mirror = _mirror(tmp_path, monkeypatch, email)
    pauses: list[float] = []

    async def fake_wait(seconds):
        if seconds > 60:
            pauses.append(seconds)
            email.fail_for.clear()  # почтовик ожил

    monkeypatch.setattr(mirror, '_wait', fake_wait)
    await mirror.start(4, user_ids=list(range(1, 11)), message_text='x')
    await _wait_tasks(mirror)

    assert len(pauses) == 1
    assert len(email.sent) == 20  # 10 отказов, затем те же 10 ушли


def test_wait_lasts_until_next_utc_day():
    from datetime import UTC, datetime

    from app.services.broadcast_email_mirror import _seconds_until_next_utc_day

    assert _seconds_until_next_utc_day(datetime(2026, 11, 16, 23, 0, tzinfo=UTC)) == 3600 + 30
    assert _seconds_until_next_utc_day(datetime(2026, 11, 16, 0, 0, tzinfo=UTC)) == 24 * 3600 + 30
