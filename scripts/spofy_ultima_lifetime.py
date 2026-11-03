"""Spofy: перевести уже купленные ULTIMA на «Навсегда» (end_date = 31.12.2099).

До этого ULTIMA продавалась как 2222 дня — у покупателей дата в 2032–2044 году.
Теперь бессрочный срок хранится одной отметкой (app/utils/lifetime.py), и тем, у
кого ULTIMA уже есть, ставим её же. Дата пишется и в БД, и в панель.

Охват (--scope):
  lifetime  ULTIMA с датой окончания от 2031 года: куплена как «вечная» (2222 дня).
  paid      lifetime + все, кто платил за ULTIMA от 4000 ₽ (в т.ч. истёкшие: им
            подписка возвращается в active).
  all       любая не-триальная подписка на тарифах «вечного» типа (switch_full_price).

Запуск (в контейнере бота):
    python -m scripts.spofy_ultima_lifetime --scope paid          # холостой прогон, только отчёт
    python -m scripts.spofy_ultima_lifetime --scope paid --apply  # записать

Перед записью снимок затрагиваемых строк (id, user_id, status, end_date)
сохраняется в LOG_DIR/ultima_lifetime_backup_<время>.json — по нему можно откатить.
Отключённые (disabled) подписки статус не меняют: их выключил админ или система.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, exists, func, or_, select

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import Subscription, SubscriptionStatus, Tariff, Transaction
from app.services.subscription_service import SubscriptionService
from app.services.system_settings_service import bot_configuration_service
from app.utils.lifetime import LIFETIME_END


_LIFETIME_BOUGHT_FROM = datetime(2031, 1, 1, tzinfo=UTC)
_MIN_PAID_KOPEKS = 400_000


async def _select(db, scope: str) -> list[Subscription]:
    lifetime_tariff_ids = select(Tariff.id).where(Tariff.switch_full_price.is_(True))
    base = and_(
        Subscription.tariff_id.in_(lifetime_tariff_ids),
        Subscription.is_trial.is_(False),
        Subscription.end_date < LIFETIME_END,
    )
    bought_lifetime = Subscription.end_date >= _LIFETIME_BOUGHT_FROM
    paid_for_it = exists().where(
        Transaction.user_id == Subscription.user_id,
        Transaction.type == 'subscription_payment',
        Transaction.is_completed.is_(True),
        func.abs(Transaction.amount_kopeks) >= _MIN_PAID_KOPEKS,
        Transaction.description.ilike('%ULTIMA%'),
    )
    if scope == 'lifetime':
        condition = and_(base, bought_lifetime)
    elif scope == 'paid':
        condition = and_(base, or_(bought_lifetime, paid_for_it))
    else:
        condition = base
    result = await db.execute(select(Subscription).where(condition).order_by(Subscription.id))
    return list(result.scalars().all())


def _backup(rows: list[Subscription]) -> Path:
    directory = Path(os.environ.get('ULTIMA_BACKUP_DIR') or settings.LOG_DIR or 'logs')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'ultima_lifetime_backup_{datetime.now(UTC).strftime("%Y%m%d-%H%M%S")}.json'
    path.write_text(
        json.dumps(
            [
                {
                    'id': s.id,
                    'user_id': s.user_id,
                    'status': s.status,
                    'end_date': s.end_date.isoformat() if s.end_date else None,
                }
                for s in rows
            ],
            ensure_ascii=False,
            indent=1,
        )
    )
    return path


async def main(scope: str, apply: bool) -> int:
    # Настройки из кабинета (system_settings) — как в scripts/backfill_remnawave_ids.py.
    await bot_configuration_service.initialize(sync_web_api_token=False)

    async with AsyncSessionLocal() as db:
        rows = await _select(db, scope)
        by_status: dict[str, int] = {}
        for sub in rows:
            by_status[sub.status] = by_status.get(sub.status, 0) + 1
        print(f'scope={scope}: {len(rows)} подписок {by_status}')
        for sub in rows:
            print(f'  sub {sub.id} user {sub.user_id} {sub.status} {sub.end_date:%Y-%m-%d}')
        if not apply or not rows:
            print('Холостой прогон — ничего не записано.' if not apply else 'Нечего делать.')
            return 0

        backup = _backup(rows)
        print(f'Снимок: {backup}')

        now = datetime.now(UTC)
        for sub in rows:
            sub.end_date = LIFETIME_END
            if sub.status == SubscriptionStatus.EXPIRED.value:
                sub.status = SubscriptionStatus.ACTIVE.value
            sub.updated_at = now
        await db.commit()
        print(f'БД: {len(rows)} → {LIFETIME_END:%d.%m.%Y}')

        service = SubscriptionService()
        failed: list[int] = []
        for sub in rows:
            try:
                await db.refresh(sub)
                if await service.update_remnawave_user(db, sub) is None:
                    failed.append(sub.id)
            except Exception as error:  # продолжаем: остальные не должны ждать одного
                print(f'  панель: sub {sub.id} ошибка {error}')
                failed.append(sub.id)
            await asyncio.sleep(0.2)  # не душим панель
        print(f'Панель: обновлено {len(rows) - len(failed)}, ошибок {len(failed)} {failed or ""}')
        return 1 if failed else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--scope', choices=('lifetime', 'paid', 'all'), required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.scope, args.apply)))
