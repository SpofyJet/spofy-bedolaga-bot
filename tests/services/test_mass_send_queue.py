"""Очередь массовых отправок и возобновление рассылок после перезапуска бота; журнал решений."""

import asyncio
import contextlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import Base, BroadcastHistory, DecisionLog, MassSendJob, User
from app.services import broadcast_service as broadcast_module, decision_log, mass_send_service as module
from app.services.broadcast_service import BroadcastConfig, BroadcastMediaConfig, BroadcastService


@contextlib.asynccontextmanager
async def _db(monkeypatch):
    stub = sys.modules.get('aiosqlite')
    if stub is not None and not hasattr(stub, 'connect'):
        monkeypatch.delitem(sys.modules, 'aiosqlite', raising=False)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[User.__table__, MassSendJob.__table__, DecisionLog.__table__, BroadcastHistory.__table__]
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    for target in (module, decision_log, broadcast_module):
        monkeypatch.setattr(target, 'AsyncSessionLocal', factory)
    try:
        yield factory
    finally:
        await engine.dispose()


def _service(monkeypatch, *, send=None):
    from app.database.crud import promo_offer_template as templates
    from app.handlers.admin import promo_offers

    service = module.MassSendService()
    service.set_bot(MagicMock(send_message=AsyncMock()))
    sender = send or AsyncMock(side_effect=lambda bot, tpl, admin, db, users, **kw: (len(users), 0, 0))
    monkeypatch.setattr(promo_offers, '_send_offer_to_users', sender)
    monkeypatch.setattr(templates, 'get_promo_offer_template_by_id', AsyncMock(return_value=SimpleNamespace(id=4)))
    monkeypatch.setattr(
        module, '_load_users', AsyncMock(side_effect=lambda db, ids: [SimpleNamespace(id=i) for i in ids])
    )
    return service, sender


async def _create(service, ids):
    return await service.create_promo_offer_job(
        template_id=4, segment='paid_expired', admin_user_id=1, chat_id=77, language='ru',
        user_ids=ids, effect_type='tariff_discount', squad_name=None, skipped=3,
    )  # fmt: skip


async def _wait(service, job_id):
    task = service._tasks.get(job_id)
    if task is not None:
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _job(factory, job_id):
    async with factory() as db:
        return await db.get(MassSendJob, job_id)


async def test_job_is_processed_in_batches_and_the_admin_gets_the_summary(monkeypatch):
    async with _db(monkeypatch) as factory:
        service, sender = _service(monkeypatch)
        job_id = await _create(service, list(range(1, 101)))
        await _wait(service, job_id)

        job = await _job(factory, job_id)
        assert (job.status, job.cursor, job.sent, job.total) == ('done', 100, 100, 100)
        assert sender.await_count == 3  # 40 + 40 + 20
        service._bot.send_message.assert_awaited_once()
        assert 'Рассылка завершена' in service._bot.send_message.await_args.kwargs['text']
        async with factory() as db:
            kinds = {row[0] for row in (await db.execute(select(DecisionLog.kind))).all()}
        assert {'mass_send_started', 'mass_send_finished'} <= kinds


async def test_restart_continues_from_the_saved_position_without_resending(monkeypatch):
    async with _db(monkeypatch) as factory:
        service, sender = _service(monkeypatch)
        async with factory() as db:
            db.add(MassSendJob(
                kind='promo_offer', status='running', cursor=40, total=100, sent=40,
                recipient_ids=list(range(1, 101)),
                params={'template_id': 4, 'admin_user_id': 1, 'chat_id': 77, 'language': 'ru',
                        'effect_type': 'tariff_discount', 'squad_name': None, 'skipped': 0},
            ))  # fmt: skip
            await db.commit()

        assert await service.resume_unfinished() == 1
        await _wait(service, 1)

        first_batch = sender.await_args_list[0].args[4]  # users первой порции после возобновления
        assert next(u.id for u in first_batch) == 41  # первые 40 уже получили — их не трогаем
        job = await _job(factory, 1)
        assert (job.status, job.cursor, job.sent) == ('done', 100, 100)
        assert sender.await_count == 2  # 41–80 и 81–100


async def test_stopping_the_bot_keeps_the_job_resumable(monkeypatch):
    async with _db(monkeypatch) as factory:
        calls = {'n': 0}

        async def flaky(bot, tpl, admin, db, users, **kw):
            calls['n'] += 1
            if calls['n'] == 2:
                raise asyncio.CancelledError  # бот останавливается посреди отправки
            return len(users), 0, 0

        service, _sender = _service(monkeypatch, send=AsyncMock(side_effect=flaky))
        job_id = await _create(service, list(range(1, 101)))
        await _wait(service, job_id)

        job = await _job(factory, job_id)
        assert job.status == 'running' and job.cursor == 40  # не 'failed': после старта продолжится
        service._bot.send_message.assert_not_awaited()


async def test_an_error_marks_the_job_failed_and_tells_the_admin(monkeypatch):
    async with _db(monkeypatch) as factory:
        service, _ = _service(monkeypatch, send=AsyncMock(side_effect=RuntimeError('нет доступа')))
        job_id = await _create(service, [1, 2, 3])
        await _wait(service, job_id)

        job = await _job(factory, job_id)
        assert job.status == 'failed' and 'нет доступа' in job.error
        assert 'остановилась с ошибкой' in service._bot.send_message.await_args.kwargs['text']


async def test_a_cancelled_job_is_not_processed(monkeypatch):
    async with _db(monkeypatch) as factory:
        service, sender = _service(monkeypatch)
        async with factory() as db:
            db.add(
                MassSendJob(
                    kind='promo_offer', status='queued', recipient_ids=[1, 2], total=2, params={'template_id': 4}
                )
            )
            await db.commit()
        assert await service.cancel(1) is True
        assert await service.cancel(1) is False  # повторно отменять нечего
        service.start(1)
        await _wait(service, 1)
        sender.assert_not_awaited()


async def test_finished_jobs_are_not_resumed(monkeypatch):
    async with _db(monkeypatch) as factory:
        service, sender = _service(monkeypatch)
        async with factory() as db:
            db.add(
                MassSendJob(kind='promo_offer', status='done', recipient_ids=[1], total=1, params={'template_id': 4})
            )
            await db.commit()
        assert await service.resume_unfinished() == 0


# ==================== обычные рассылки ====================


def test_broadcast_config_survives_a_round_trip():
    config = BroadcastConfig(
        target='all', message_text='Привет', selected_buttons=['home'],
        media=BroadcastMediaConfig(type='photo', file_id='F', caption='подпись'),
        initiator_name='admin', custom_buttons=[{'text': 'Купить', 'url': 'https://x'}], category='promo',
    )  # fmt: skip
    restored = BroadcastService._deserialize_config(BroadcastService._serialize_config(config))
    assert restored == config


async def test_interrupted_broadcast_is_resumed_from_its_position(monkeypatch):
    async with _db(monkeypatch) as factory:
        config = BroadcastConfig(target='all', message_text='Привет', selected_buttons=[])
        async with factory() as db:
            db.add(BroadcastHistory(
                target_type='all', message_text='Привет', status='in_progress', recipient_ids=[1, 2, 3, 4],
                resume_cursor=2, resume_config=BroadcastService._serialize_config(config), total_count=4,
            ))  # fmt: skip
            db.add(BroadcastHistory(target_type='all', status='in_progress'))  # старая запись без получателей
            db.add(BroadcastHistory(
                target_type='all', status='in_progress', recipient_ids=[1], resume_cursor=1,
                resume_config=BroadcastService._serialize_config(config),
            ))  # fmt: skip
            await db.commit()

        service = BroadcastService()
        service.start_broadcast = AsyncMock()
        assert await service.resume_interrupted() == 1  # только первая: у остальных нечего продолжать
        assert service.start_broadcast.await_args.kwargs == {'resume': True}


# ==================== журнал решений ====================


async def test_decision_log_records_counts_and_never_breaks_the_caller(monkeypatch):
    async with _db(monkeypatch) as factory:
        await decision_log.record_decision(
            'abuse_trial_removed', 'второй аккаунт на устройстве', user_id=5, panel_user_id=9
        )
        await decision_log.record_decision('abuse_trial_removed', 'ещё один')
        await decision_log.record_decision('friend_reward_blocked', 'общее устройство', details={'inviter_id': 2})
        async with factory() as db:
            counts = dict(await decision_log.decision_counts(db, days=7))
            last = await decision_log.recent_decisions(db, limit=5, kind='friend_reward_blocked')
        assert counts == {'abuse_trial_removed': 2, 'friend_reward_blocked': 1}
        assert last[0].details == {'inviter_id': 2}

    monkeypatch.setattr(decision_log, 'AsyncSessionLocal', MagicMock(side_effect=RuntimeError('база недоступна')))
    await decision_log.record_decision('x', 'не должно бросать')  # журнал не ломает то, что журналирует
