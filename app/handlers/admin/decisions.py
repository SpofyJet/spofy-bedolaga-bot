"""`/decisions [вид]` — последние решения бота и счётчики за неделю (антиабуз, награды, рассылки)."""

import html

from aiogram import Dispatcher, types
from aiogram.filters import Command, CommandObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.services.decision_log import decision_counts, recent_decisions
from app.utils.decorators import admin_required, error_handler
from app.utils.timezone import format_local_datetime


@admin_required
@error_handler
async def decisions_command(message: types.Message, db_user: User, db: AsyncSession, command: CommandObject):
    kind = (command.args or '').strip() or None
    counts = await decision_counts(db, days=7)
    rows = await recent_decisions(db, limit=15, kind=kind)

    lines = ['🧾 <b>Журнал решений</b>']
    if counts:
        lines.append('За 7 дней: ' + ', '.join(f'{html.escape(k)}: {n}' for k, n in counts))
    else:
        lines.append('За 7 дней записей нет.')
    lines.append('')
    if not rows:
        lines.append('Записей по этому запросу нет.')
    for row in rows:
        when = format_local_datetime(row.created_at, '%d.%m %H:%M')
        who = f' · user {row.user_id}' if row.user_id else ''
        lines.append(f'{when} <b>{html.escape(row.kind)}</b>{who}\n  {html.escape(row.summary or "")[:240]}')
    lines.append('\nФильтр: <code>/decisions abuse_trial_removed</code>')
    await message.reply('\n'.join(lines))


def register_handlers(dp: Dispatcher) -> None:
    dp.message.register(decisions_command, Command('decisions'))
