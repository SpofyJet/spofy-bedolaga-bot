"""Очередь массовых отправок: задание лежит в базе и переживает перезапуск бота.

Что было: рассылка предложений шла прямо в обработчике кнопки админа. Перезапуск бота обрывал её на полпути
(так однажды остановились на 4 779 из 19 887), а итоговое сообщение падало, потому что за минуты отправки
закрывалось соединение с базой, открытое обработчиком.

Как теперь: ``create_promo_offer_job`` записывает получателей в ``mass_send_jobs`` и сразу возвращает управление.
Фоновая задача берёт порции по ``BATCH`` человек со своей свежей сессией и после каждой порции сохраняет позицию
(``cursor``) и счётчики. При старте бота ``resume_unfinished`` продолжает незавершённые задания с сохранённой
позиции: повторно получат только люди из последней порции, которая оборвалась на середине.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.database import AsyncSessionLocal
from app.database.models import MassSendJob, Subscription, User
from app.services.decision_log import (
    KIND_MASS_SEND_FINISHED,
    KIND_MASS_SEND_RESUMED,
    KIND_MASS_SEND_STARTED,
    record_decision,
)


logger = structlog.get_logger(__name__)

KIND_PROMO_OFFER = 'promo_offer'
BATCH = 40  # размер порции = максимум людей, получающих сообщение повторно после обрыва посреди порции
UNFINISHED = ('queued', 'running')


async def _load_users(db, ids: list[int]) -> list[User]:
    """Люди порции в порядке очереди, с теми же связями, что у выборки сегмента."""
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.subscriptions).selectinload(Subscription.tariff),
            selectinload(User.promo_group),
            selectinload(User.referrer),
        )
        .where(User.id.in_(ids))
    )
    by_id = {user.id: user for user in result.scalars().unique().all()}
    return [by_id[i] for i in ids if i in by_id]


class MassSendService:
    def __init__(self) -> None:
        self._bot: Bot | None = None
        self._tasks: dict[int, asyncio.Task] = {}

    def set_bot(self, bot: Bot) -> None:
        self._bot = bot

    # ------------------------------------------------------------------ #
    # Создание и запуск
    # ------------------------------------------------------------------ #
    async def create_promo_offer_job(
        self,
        *,
        template_id: int,
        segment: str,
        admin_user_id: int,
        chat_id: int,
        language: str,
        user_ids: list[int],
        effect_type: str,
        squad_name: str | None,
        skipped: int = 0,
    ) -> int:
        params: dict[str, Any] = {
            'template_id': template_id,
            'segment': segment,
            'admin_user_id': admin_user_id,
            'chat_id': chat_id,
            'language': language,
            'effect_type': effect_type,
            'squad_name': squad_name,
            'skipped': skipped,
        }
        async with AsyncSessionLocal() as db:
            job = MassSendJob(
                kind=KIND_PROMO_OFFER, status='queued', params=params, recipient_ids=list(user_ids), total=len(user_ids)
            )
            db.add(job)
            await db.commit()
            job_id = job.id
        await record_decision(
            KIND_MASS_SEND_STARTED,
            f'Рассылка предложения #{template_id} сегменту «{segment}»: {len(user_ids)} получателей (задание {job_id})',
            details={'job_id': job_id, 'template_id': template_id, 'segment': segment, 'total': len(user_ids)},
        )
        self.start(job_id)
        return job_id

    def start(self, job_id: int) -> None:
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            return
        task = asyncio.create_task(self._run(job_id), name=f'mass-send-{job_id}')
        self._tasks[job_id] = task
        task.add_done_callback(lambda _t, jid=job_id: self._tasks.pop(jid, None))

    async def resume_unfinished(self) -> int:
        """При старте бота: продолжить задания, которые перезапуск оборвал. Возвращает их число."""
        async with AsyncSessionLocal() as db:
            rows = await db.execute(select(MassSendJob).where(MassSendJob.status.in_(UNFINISHED)))
            jobs = list(rows.scalars().all())
        for job in jobs:
            logger.warning(
                'Продолжаем массовую отправку после перезапуска', job_id=job.id, cursor=job.cursor, total=job.total
            )
            await record_decision(
                KIND_MASS_SEND_RESUMED,
                f'Задание {job.id} продолжено после перезапуска бота: обработано {job.cursor} из {job.total}',
                details={'job_id': job.id, 'cursor': job.cursor, 'total': job.total},
            )
            self.start(job.id)
        return len(jobs)

    async def cancel(self, job_id: int) -> bool:
        async with AsyncSessionLocal() as db:
            job = await db.get(MassSendJob, job_id)
            if job is None or job.status not in UNFINISHED:
                return False
            job.status = 'cancelled'
            job.finished_at = datetime.now(UTC)
            await db.commit()
        return True

    # ------------------------------------------------------------------ #
    # Выполнение
    # ------------------------------------------------------------------ #
    async def _run(self, job_id: int) -> None:
        if self._bot is None:
            logger.error('Массовая отправка: бот не подключён', job_id=job_id)
            return
        from app.database.crud.promo_offer_template import get_promo_offer_template_by_id
        from app.handlers.admin.promo_offers import _send_offer_to_users

        try:
            while True:
                async with AsyncSessionLocal() as db:
                    job = await db.get(MassSendJob, job_id)
                    if job is None or job.status not in UNFINISHED:
                        return
                    if job.status == 'queued':
                        job.status = 'running'
                    params = dict(job.params or {})
                    ids = list((job.recipient_ids or [])[job.cursor : job.cursor + BATCH])
                    if not ids:
                        break
                    template = await get_promo_offer_template_by_id(db, int(params['template_id']))
                    if template is None:
                        raise RuntimeError(f'предложение #{params["template_id"]} удалено')
                    admin = await db.get(User, int(params['admin_user_id']))
                    users = await _load_users(db, ids)
                    sent, failed, already = await _send_offer_to_users(
                        self._bot,
                        template,
                        admin,
                        db,
                        users,
                        squad_name=params.get('squad_name'),
                        effect_type=params.get('effect_type', 'percent_discount'),
                    )
                    # Позиция сохраняется после каждой порции: обрыв потеряет не больше BATCH получателей
                    job.cursor += len(ids)
                    job.sent += sent
                    job.failed += failed + (len(ids) - len(users))  # исчезнувшие из базы люди = недоставлено
                    job.already += already
                    await db.commit()
        except asyncio.CancelledError:
            raise  # остановка бота: задание остаётся 'running' и подхватится при следующем старте
        except Exception as error:
            logger.exception('Массовая отправка завершилась ошибкой', job_id=job_id, error=str(error))
            await self._finish(job_id, status='failed', error=str(error))
            return
        await self._finish(job_id, status='done')

    async def _finish(self, job_id: int, *, status: str, error: str | None = None) -> None:
        async with AsyncSessionLocal() as db:
            job = await db.get(MassSendJob, job_id)
            if job is None:
                return
            job.status = status
            job.error = error
            job.finished_at = datetime.now(UTC)
            await db.commit()
            snapshot = {
                'sent': job.sent,
                'failed': job.failed,
                'already': job.already,
                'total': job.total,
                'params': dict(job.params or {}),
            }
        await record_decision(
            KIND_MASS_SEND_FINISHED,
            f'Задание {job_id}: {status}, отправлено {snapshot["sent"]}, ошибок {snapshot["failed"]}, '
            f'уже было {snapshot["already"]} из {snapshot["total"]}',
            details={'job_id': job_id, 'status': status, **{k: v for k, v in snapshot.items() if k != 'params'}},
        )
        await self._notify_admin(job_id, status, error, snapshot)

    async def _notify_admin(self, job_id: int, status: str, error: str | None, snapshot: dict[str, Any]) -> None:
        if self._bot is None:
            return
        from app.database.crud.promo_offer_template import get_promo_offer_template_by_id
        from app.localization.texts import get_texts

        params = snapshot['params']
        texts = get_texts(params.get('language') or 'ru')
        if status == 'done':
            summary = texts.t(
                'ADMIN_PROMO_OFFER_RESULT', '📬 Рассылка завершена\nОтправлено: {sent}\nОшибок: {failed}'
            ).format(sent=snapshot['sent'], failed=snapshot['failed'])
            if snapshot['already'] > 0:
                summary += '\n' + texts.t(
                    'ADMIN_PROMO_OFFER_ALREADY',
                    'Уже получали это предложение (или у них действует другая скидка): {already}',
                ).format(already=snapshot['already'])
            if params.get('skipped'):
                summary += '\n' + texts.t('ADMIN_PROMO_OFFER_SKIPPED', 'Пропущено: {skipped} (уже есть доступ)').format(
                    skipped=params['skipped']
                )
        else:
            summary = f'❌ Рассылка (задание {job_id}) остановилась с ошибкой: {error}\nОтправлено: {snapshot["sent"]}'
        rows: list[list[InlineKeyboardButton]] = []
        try:
            async with AsyncSessionLocal() as db:
                template = await get_promo_offer_template_by_id(db, int(params['template_id']))
            if template is not None:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=texts.t('ADMIN_PROMO_OFFER_BACK_TO_TEMPLATE', '↩️ К предложению'),
                            callback_data=f'promo_offer_{template.id}',
                        )
                    ]
                )
        except Exception:
            pass
        rows.append(
            [
                InlineKeyboardButton(
                    text=texts.t('ADMIN_PROMO_OFFER_BACK_TO_LIST', '⬅️ К промопредложениям'),
                    callback_data='admin_promo_offers',
                )
            ]
        )
        try:
            await self._bot.send_message(
                chat_id=params['chat_id'],
                text=summary,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                parse_mode='HTML',
            )
        except Exception as error_send:
            logger.warning('Итог массовой отправки не доставлен админу', job_id=job_id, error=str(error_send))


mass_send_service = MassSendService()
