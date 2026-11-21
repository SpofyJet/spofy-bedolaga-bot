import json
import os
import shutil
import subprocess
import zlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramNotFound
from aiogram.methods import SendWidget

from app.config import settings
from app.services import subscription_widget as sw


NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
BYPASS = 'bypass-squad'


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, 'SUBSCRIPTION_WIDGET_ENABLED', True, raising=False)
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', BYPASS, raising=False)
    monkeypatch.setattr(sw, '_unavailable', False)


def _sub(**over):
    base = {
        'status': 'active',
        'end_date': NOW + timedelta(days=24),
        'is_trial': False,
        'device_limit': 3,
        'traffic_used_gb': 12.345,
        'traffic_limit_gb': 100,
        'connected_squads': ['main', BYPASS],
        'bypass_suspended_at': None,
        'tariff_id': 1,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _user(balance=15000):
    return SimpleNamespace(balance_kopeks=balance)


def _data(sub=None, tariff=None, devices=2, friends=0, user=None):
    return sw.card_data(
        user or _user(),
        sub or _sub(),
        tariff=tariff or SimpleNamespace(name='⭐ Стандартный', is_daily=False),
        devices=devices,
        from_friends_kopeks=friends,
        now=NOW,
    )


@pytest.mark.parametrize('lang', sorted(sw.CARD_HTML))
def test_card_html_fits_telegram_limits(lang):
    raw = sw.CARD_HTML[lang].encode()
    assert len(raw) <= 32768
    assert len(zlib.compress(raw, 9)) <= 4096
    assert b'\x00' not in raw
    assert b'__L__' not in raw


def test_unknown_language_gets_russian_card():
    assert sw.card_html('uk') == sw.CARD_HTML['ru']
    assert sw.card_html(None) == sw.CARD_HTML['ru']
    assert sw.card_html('en-US') == sw.CARD_HTML['en']


def test_active_paid_card():
    data = _data(friends=5099)
    assert data['s'] == 'a'
    assert data['e'] == int((NOW + timedelta(days=24)).timestamp())
    assert (data['dc'], data['dl']) == (2, 3)
    assert (data['tu'], data['tl']) == (12.35, 100)
    assert data['n'] == '⭐ Стандартный'
    assert (data['b'], data['f']) == (150, 50)
    assert not data['tr'] and not data['li'] and not data['lt'] and not data['bx']


@pytest.mark.parametrize(
    ('over', 'state', 'limited'),
    [
        ({'status': 'limited'}, 'a', True),
        ({'status': 'limited', 'end_date': NOW - timedelta(days=1)}, 'a', True),
        ({'status': 'expired'}, 'x', False),
        ({'status': 'disabled'}, 'x', False),
        ({'status': 'active', 'end_date': NOW - timedelta(minutes=1)}, 'x', False),
    ],
)
def test_card_states(over, state, limited):
    data = _data(_sub(**over))
    assert data['s'] == state
    assert data['li'] is limited


def test_unknown_status_has_no_card():
    assert _data(_sub(status='pending')) is None


def test_unknown_devices_are_left_out():
    assert 'dc' not in _data(devices=None)


def test_trial_and_lifetime_never_say_bypass_missing():
    no_bypass = {'connected_squads': ['main']}
    assert _data(_sub(**no_bypass))['bx'] is True
    assert _data(_sub(is_trial=True, **no_bypass))['bx'] is False
    assert _data(_sub(end_date=datetime(2099, 12, 31, tzinfo=UTC), **no_bypass))['bx'] is False
    assert _data(_sub(**no_bypass), tariff=SimpleNamespace(name='Сутки', is_daily=True))['bx'] is False


def test_bypass_missing_needs_configured_squad(monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', '', raising=False)
    assert _data(_sub(connected_squads=['main']))['bx'] is False


def test_bypass_quota_flag():
    assert _data()['bq'] is True
    assert _data(_sub(traffic_limit_gb=0))['bq'] is False


def test_long_tariff_name_is_cut_to_fit():
    data = _data(tariff=SimpleNamespace(name='Тариф ' * 400, is_daily=False))
    encoded = sw.encode_card_data(data)
    assert len(encoded.encode()) <= sw.DATA_LIMIT
    assert json.loads(encoded)['n'].startswith('Тариф')


def test_data_that_cannot_fit_raises():
    with pytest.raises(ValueError, match='1024'):
        sw.encode_card_data({'v': 1, 'x': 'я' * 600})


def _callback(chat_type='private'):
    message = MagicMock()
    message.chat.id = 777
    message.chat.type = chat_type
    message.delete = AsyncMock()
    callback = MagicMock()
    callback.message = message
    callback.bot.send_widget = AsyncMock()
    return callback


async def _send(callback, data=None, caption_parts=('💳 Автопродление: выключено',)):
    return await sw.try_send_subscription_widget(
        callback,
        language='ru',
        data=data or _data(),
        caption_parts=list(caption_parts),
        keyboard=MagicMock(),
    )


@pytest.mark.asyncio
async def test_widget_is_sent_before_old_screen_is_deleted():
    callback = _callback()
    order = []
    callback.bot.send_widget.side_effect = lambda **kw: order.append('send')
    callback.message.delete.side_effect = lambda: order.append('delete')

    assert await _send(callback) is True
    assert order == ['send', 'delete']
    kwargs = callback.bot.send_widget.await_args.kwargs
    assert kwargs['chat_id'] == 777
    assert kwargs['html'] == sw.CARD_HTML['ru']
    assert kwargs['allow_queries'] is True
    assert kwargs['caption'] == '💳 Автопродление: выключено'
    assert json.loads(kwargs['chat_data'])['s'] == 'a'


@pytest.mark.asyncio
async def test_empty_caption_is_not_sent():
    callback = _callback()
    assert await _send(callback, caption_parts=['', '\n']) is True
    kwargs = callback.bot.send_widget.await_args.kwargs
    assert kwargs['caption'] is None
    assert kwargs['parse_mode'] is None


@pytest.mark.asyncio
async def test_failed_send_keeps_old_screen():
    callback = _callback()
    callback.bot.send_widget.side_effect = TelegramBadRequest(
        method=SendWidget(chat_id=1, html='x'), message='Bad Request: INPUT_MEDIA_WIDGET_TOO_LARGE'
    )
    assert await _send(callback) is False
    callback.message.delete.assert_not_awaited()
    assert sw.widget_enabled() is True


@pytest.mark.asyncio
async def test_network_error_falls_back_without_disabling():
    callback = _callback()
    callback.bot.send_widget.side_effect = TelegramNetworkError(method=SendWidget(chat_id=1, html='x'), message='x')
    assert await _send(callback) is False
    assert sw.widget_enabled() is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'error',
    [
        TelegramNotFound(method=SendWidget(chat_id=1, html='x'), message='Not Found'),
        TelegramBadRequest(method=SendWidget(chat_id=1, html='x'), message='Bad Request: method not found'),
    ],
)
async def test_server_without_widgets_turns_card_off_until_restart(error):
    callback = _callback()
    callback.bot.send_widget.side_effect = error
    assert await _send(callback) is False
    assert sw.widget_enabled() is False
    second = _callback()
    assert await _send(second) is False
    second.bot.send_widget.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_delete_still_counts_as_shown():
    callback = _callback()
    callback.message.delete.side_effect = TelegramBadRequest(
        method=SendWidget(chat_id=1, html='x'), message='message to delete not found'
    )
    assert await _send(callback) is True


@pytest.mark.asyncio
@pytest.mark.parametrize('chat_type', ['group', 'supergroup'])
async def test_only_private_chats(chat_type):
    callback = _callback(chat_type)
    assert await _send(callback) is False
    callback.bot.send_widget.assert_not_awaited()


@pytest.mark.asyncio
async def test_switched_off_or_no_data(monkeypatch):
    callback = _callback()
    assert (
        await sw.try_send_subscription_widget(
            callback, language='ru', data=None, caption_parts=[], keyboard=MagicMock()
        )
        is False
    )
    monkeypatch.setattr(settings, 'SUBSCRIPTION_WIDGET_ENABLED', False, raising=False)
    assert await _send(callback) is False
    callback.bot.send_widget.assert_not_awaited()


@pytest.mark.asyncio
async def test_caption_over_limit_keeps_classic_screen():
    callback = _callback()
    assert await _send(callback, caption_parts=['x' * 1025]) is False
    callback.bot.send_widget.assert_not_awaited()


def _query(data='r', chat_id=777, from_id=777, chat_type='private'):
    query = MagicMock()
    query.data = data
    query.from_user.id = from_id
    query.chat = SimpleNamespace(id=chat_id, type=chat_type) if chat_id else None
    query.answer = AsyncMock()
    return query


@pytest.mark.asyncio
async def test_query_answers_fresh_data(monkeypatch):
    fresh = AsyncMock(return_value={'v': 1, 's': 'a', 'b': 10})
    monkeypatch.setattr(sw, '_fresh_card_data', fresh)
    query = _query()
    await sw.handle_subscription_widget_query(query)
    fresh.assert_awaited_once_with(777)
    assert json.loads(query.answer.await_args.kwargs['data']) == {'v': 1, 's': 'a', 'b': 10}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'query',
    [
        _query(data='other'),
        _query(chat_id=555),
        _query(chat_id=None),
        _query(chat_type='group'),
    ],
)
async def test_query_from_elsewhere_gets_empty_answer(monkeypatch, query):
    fresh = AsyncMock()
    monkeypatch.setattr(sw, '_fresh_card_data', fresh)
    await sw.handle_subscription_widget_query(query)
    fresh.assert_not_awaited()
    query.answer.assert_awaited_once_with(data=None)


@pytest.mark.asyncio
async def test_query_when_switched_off(monkeypatch):
    monkeypatch.setattr(settings, 'SUBSCRIPTION_WIDGET_ENABLED', False, raising=False)
    fresh = AsyncMock()
    monkeypatch.setattr(sw, '_fresh_card_data', fresh)
    query = _query()
    await sw.handle_subscription_widget_query(query)
    fresh.assert_not_awaited()
    query.answer.assert_awaited_once_with(data=None)


@pytest.mark.asyncio
async def test_query_survives_database_failure(monkeypatch):
    monkeypatch.setattr(sw, '_fresh_card_data', AsyncMock(side_effect=OSError('db down')))
    query = _query()
    await sw.handle_subscription_widget_query(query)
    query.answer.assert_awaited_once_with(data=None)


@pytest.mark.asyncio
async def test_query_answer_error_is_swallowed(monkeypatch):
    monkeypatch.setattr(sw, '_fresh_card_data', AsyncMock(return_value=None))
    query = _query()
    query.answer.side_effect = TelegramBadRequest(method=SendWidget(chat_id=1, html='x'), message='query is too old')
    await sw.handle_subscription_widget_query(query)


NODE = shutil.which('node')
STUB = """
const html=require('fs').readFileSync(0,'utf8');
const script=html.slice(html.indexOf('<script>')+8,html.lastIndexOf('</script>'));
const el={innerHTML:''};
const handlers={};
global.document={getElementById:()=>el};
global.window={TelegramWidget:{colorScheme:process.argv[2],themeParams:{hint_color:'#707579'},chatData:process.argv[1],
 onEvent:(t,f)=>{handlers[t]=f},request:()=>new Promise(()=>{}),ready:()=>{}}};
global.Date=class extends Date{constructor(...a){super(...(a.length?a:[%NOW%]))}static now(){return %NOW%}};
eval(script);
process.stdout.write(el.innerHTML.replace(/<[^>]+>/g,'|').replace(/\\|+/g,'|'));
"""


def _run(raw, lang='ru', scheme='light'):
    stub = STUB.replace('%NOW%', str(int(NOW.timestamp() * 1000)))
    result = subprocess.run(  # noqa: S603 — карточка из репозитория
        [NODE, '-e', stub, '--', raw, scheme],
        input=sw.CARD_HTML[lang],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
        env={'TZ': 'UTC', 'PATH': os.environ.get('PATH', '')},
    )
    return result.stdout.replace('\u00a0', ' ')


def _render(data, lang='ru', scheme='light'):
    return _run(json.dumps(data), lang, scheme)


def _js(over=None, **kw):
    data = dict(_data(**kw))
    data.update(over or {})
    return data


@pytest.mark.skipif(NODE is None, reason='нет node')
@pytest.mark.parametrize(
    ('over', 'sub', 'expected', 'absent'),
    [
        (
            None,
            {},
            [
                'VPN работает',
                'до 15 декабря · ещё 24 дня',
                '2 из 3',
                'подключено',
                '12 из 100 ГБ',
                'Стандартный',
                '150 ₽',
            ],
            ['⭐', 'Продлите'],
        ),
        (
            None,
            {'end_date': NOW + timedelta(hours=20)},
            ['VPN выключится завтра', 'оплачено до 22 ноября', 'Продлите сейчас'],
            ['Подписка|'],
        ),
        (None, {'end_date': NOW + timedelta(hours=3)}, ['VPN выключится сегодня'], []),
        (None, {'end_date': NOW + timedelta(days=3)}, ['VPN выключится через 3 дня'], []),
        (
            {'dc': 0},
            {'is_trial': True, 'end_date': NOW + timedelta(days=2)},
            ['Пробный период идёт', 'до 23 ноября · устройство не подключено'],
            ['Устройства', 'Подписка|'],
        ),
        (
            {'dc': 1, 'dl': 1},
            {'is_trial': True, 'end_date': NOW + timedelta(days=2)},
            ['VPN работает', 'пробный период · до 23 ноября', '1 из 1', 'все места заняты'],
            [],
        ),
        (None, {'status': 'limited'}, ['Трафик закончился', 'оплачено до 15 декабря'], []),
        (
            None,
            {'status': 'expired', 'end_date': NOW - timedelta(days=3)},
            ['VPN выключен', 'оплата закончилась 18 ноября', 'Продлите подписку'],
            ['Устройства', 'Трафик', 'Подписка|'],
        ),
        (
            None,
            {'status': 'expired', 'is_trial': True, 'end_date': NOW - timedelta(days=3)},
            ['пробный период закончился 18 ноября', 'Оформите подписку'],
            [],
        ),
        (
            None,
            {'end_date': datetime(2099, 12, 31, tzinfo=UTC), 'traffic_limit_gb': 0},
            ['VPN работает', 'навсегда'],
            ['Трафик', '2099'],
        ),
        (None, {'bypass_suspended_at': NOW}, ['Трафик обходов'], []),
        ({'bs': True}, {}, ['обходы выключены', 'докупите гигабайты'], []),
        (None, {'connected_squads': ['main'], 'traffic_limit_gb': 0}, ['Обходы', 'нет в тарифе'], ['Трафик']),
        (None, {'end_date': NOW + timedelta(days=400)}, ['26 декабря 2027 г.'], []),
        ({'f': 50}, {}, ['50 ₽ с друзей'], []),
        ({'tu': 0.4, 'tl': 10}, {}, ['410 МБ из 10 ГБ'], []),
        ({'tu': 1234, 'tl': 2000}, {}, ['1,2 из 2 ТБ'], []),
    ],
)
def test_card_reads_like_cabinet(over, sub, expected, absent):
    text = _render(_js(over, sub=_sub(**sub)))
    for part in expected:
        assert part in text, (part, text)
    for part in absent:
        assert part not in text, (part, text)


@pytest.mark.skipif(NODE is None, reason='нет node')
def test_card_in_english_and_dark():
    text = _render(_js(), lang='en', scheme='dark')
    assert 'VPN is on' in text
    assert 'until December 15 · 24 days left' in text
    assert '2 of 3' in text


@pytest.mark.skipif(NODE is None, reason='нет node')
@pytest.mark.parametrize('raw', ['', 'not json', '[]', 'null'])
def test_broken_chat_data_shows_empty_card(raw):
    assert 'Нет подписки' in _run(raw)


@pytest.mark.skipif(NODE is None, reason='нет node')
def test_tariff_name_html_is_escaped():
    text = _render(_js({'n': '<b>x</b>'}))
    assert '&lt;b&gt;x&lt;/b&gt;' in text
