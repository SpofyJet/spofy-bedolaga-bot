import html
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.utils.subscription_time import local_days_until
from app.utils.subscription_utils import get_display_subscription_link
from app.utils.timezone import format_local_datetime

from .common import logger
from .countries import _get_countries_info
from .devices import get_current_devices_count


async def get_subscription_cost(subscription, db: AsyncSession) -> int:
    try:
        if subscription.is_trial:
            return 0

        from app.services.pricing_engine import pricing_engine

        try:
            owner = subscription.user
        except AttributeError:
            owner = None

        result = await pricing_engine.calculate_renewal_price(db, subscription, 30, user=owner)
        total_cost = result.final_total

        logger.info('Monthly subscription cost', subscription_id=subscription.id, total_cost_kopeks=total_cost)
        return total_cost

    except Exception as e:
        logger.error('Error calculating subscription cost', error=e)
        return 0


async def get_subscription_info_text(subscription, texts, db_user, db: AsyncSession):
    devices_selection_enabled = settings.is_devices_selection_enabled()

    if devices_selection_enabled:
        devices_used = await get_current_devices_count(db_user)
    else:
        devices_used = 0
    countries_info = await _get_countries_info(subscription.connected_squads)
    ', '.join([c['name'] for c in countries_info]) if countries_info else 'Нет'

    subscription_url = get_display_subscription_link(subscription)

    if subscription.is_trial:
        status_text = '🎁 Тестовая'
        type_text = 'Триал'
    else:
        if subscription.is_active:
            status_text = '✅ Оплачена'
        else:
            status_text = '⌛ Истекла'
        type_text = 'Платная подписка'

    traffic_limit = subscription.traffic_limit_gb or 0
    if traffic_limit == 0:
        if settings.is_traffic_fixed():
            traffic_text = '∞ Безлимитный'
        else:
            traffic_text = '∞ Безлимитный'
    elif settings.is_traffic_fixed():
        traffic_text = f'{traffic_limit} ГБ'
    else:
        traffic_text = f'{traffic_limit} ГБ'

    subscription_cost = await get_subscription_cost(subscription, db)

    info_template = texts.SUBSCRIPTION_INFO

    if not devices_selection_enabled:
        info_template = info_template.replace(
            '\n📱 <b>Устройства:</b> {devices_used} / {devices_limit}',
            '',
        ).replace(
            '\n📱 <b>Devices:</b> {devices_used} / {devices_limit}',
            '',
        )

    info_text = info_template.format(
        status=status_text,
        type=type_text,
        end_date=format_local_datetime(subscription.end_date, '%d.%m.%Y %H:%M'),
        days_left=local_days_until(subscription.end_date) if subscription.end_date else 0,
        traffic_used=texts.format_traffic(subscription.traffic_used_gb, is_limit=False),
        traffic_limit=traffic_text,
        countries_count=len(subscription.connected_squads or []),
        devices_used=devices_used,
        devices_limit=subscription.device_limit,
        autopay_status='✅ Включен' if subscription.autopay_enabled else '⌛ Выключен',
    )

    if subscription_cost > 0:
        info_text += f'\n💰 <b>Стоимость подписки в месяц:</b> {texts.format_price(subscription_cost)}'

    # Отображаем докупленный трафик
    if (subscription.traffic_limit_gb or 0) > 0:  # Только для лимитированных тарифов
        from sqlalchemy import select as sql_select

        from app.database.models import TrafficPurchase

        now = datetime.now(UTC)
        purchases_query = (
            sql_select(TrafficPurchase)
            .where(TrafficPurchase.subscription_id == subscription.id)
            .where(TrafficPurchase.expires_at > now)
            .order_by(TrafficPurchase.expires_at.asc())
        )
        purchases_result = await db.execute(purchases_query)
        purchases = purchases_result.scalars().all()

        if purchases:
            info_text += '\n\n📦 <b>Докупленный трафик:</b>'

            for purchase in purchases:
                time_remaining = purchase.expires_at - now
                days_remaining = max(0, int(time_remaining.total_seconds() / 86400))

                # Генерируем прогресс-бар
                total_duration_seconds = (purchase.expires_at - purchase.created_at).total_seconds()
                elapsed_seconds = (now - purchase.created_at).total_seconds()
                progress_percent = min(
                    100.0,
                    max(0.0, (elapsed_seconds / total_duration_seconds * 100) if total_duration_seconds > 0 else 0),
                )

                bar_length = 10
                filled = int((progress_percent / 100) * bar_length)
                bar = '▰' * filled + '▱' * (bar_length - filled)

                # Форматируем дату истечения
                expire_date = format_local_datetime(purchase.expires_at, '%d.%m.%Y')

                # Формируем текст о времени
                if days_remaining == 0:
                    time_text = 'истекает сегодня'
                elif days_remaining == 1:
                    time_text = 'остался 1 день'
                elif days_remaining < 5:
                    time_text = f'осталось {days_remaining} дня'
                else:
                    time_text = f'осталось {days_remaining} дней'

                info_text += f'\n• {purchase.traffic_gb} ГБ — {time_text}'
                info_text += f'\n  {bar} {progress_percent:.0f}% | до {expire_date}'

    if subscription_url and not settings.should_hide_subscription_link():
        info_text += (
            f'\n\n🔗 <b>Ваша ссылка для импорта в VPN приложениe:</b>\n<code>{html.escape(subscription_url)}</code>'
        )

    return info_text
