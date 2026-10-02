"""Spofy: исчерпан трафик на тарифе с обходами — отключаются только обходы.

На тарифе «С обходами» трафик считают только ноды обходов (у обычных
``consumptionMultiplier = 0``), так что лимит тарифа — это квота на обходы. Раньше
на лимите панель переводила аккаунт в LIMITED и отдавала пустую подписку: человек
терял и обычные серверы. Теперь вместо этого подписка уходит в сквад Bypass-Off
(обычные инбаунды + заметки «обходы отключены»), остаётся ACTIVE, а лимит в панели
снимается (обычные ноды трафик не считают). Дата не меняется.

Состояние — ``Subscription.bypass_suspended_at``. В панель оно уходит одним
правилом (``panel_squads_for`` / ``panel_traffic_limit_bytes_for``), которым
пользуются все писатели: пока подписка помечена И её квота всё ещё исчерпана,
панель получает ``[Bypass-Off]`` и безлимит. Как только квота перестала быть
исчерпанной — докупили трафик, продлили (продление обнуляет расход), сменили
тариф, сбросили трафик — любой следующий пуш возвращает сквады тарифа, а сверка
снимает пометку и пишет человеку. Вернуть обходы при исчерпанной квоте нельзя:
панель тут же выключила бы аккаунт целиком.

Сервис с побочными эффектами (панель, база, уведомления) — в
``bypass_downgrade_service.py``; здесь только правила, без ввода-вывода.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from app.config import settings
from app.database.models import SubscriptionStatus, UserStatus


#: Погрешность сравнения расхода с лимитом: расход приходит из панели в байтах.
_EPSILON_GB = 0.01

#: Подписка с этими статусами может уйти в Bypass-Off. LIMITED — потому что
#: панель выставляет его раньше, чем приходит вебхук или сверка.
_SUSPENDABLE_STATUSES = frozenset({SubscriptionStatus.ACTIVE.value, SubscriptionStatus.LIMITED.value})


def mode() -> str:
    return settings.BYPASS_DOWNGRADE_MODE


def is_configured() -> bool:
    return bool(settings.BYPASS_SQUAD_UUID and settings.BYPASS_OFF_SQUAD_UUID)


def is_enforcing() -> bool:
    """Режим true и оба сквада заданы: подписки реально переводятся."""
    return mode() == 'true' and is_configured()


def is_observing() -> bool:
    return mode() == 'observe' and is_configured()


def quota_exhausted(subscription) -> bool:
    limit = getattr(subscription, 'traffic_limit_gb', 0) or 0
    used = getattr(subscription, 'traffic_used_gb', 0.0) or 0.0
    return limit > 0 and used >= limit - _EPSILON_GB


def is_suspension_effective(subscription) -> bool:
    """Отдавать ли панели «обходы отключены» для этой подписки прямо сейчас."""
    return (
        is_enforcing()
        and getattr(subscription, 'bypass_suspended_at', None) is not None
        and quota_exhausted(subscription)
    )


def panel_squads_for(subscription, squads: Iterable[str]) -> list[str]:
    """Сквады, которые уходят в панель: сквады тарифа или ``[Bypass-Off]``."""
    if is_suspension_effective(subscription):
        return [settings.BYPASS_OFF_SQUAD_UUID]
    return list(squads)


def panel_traffic_limit_bytes_for(subscription, limit_bytes: int) -> int:
    """Лимит для панели: в Bypass-Off — безлимит (обычные ноды считают ×0)."""
    if is_suspension_effective(subscription):
        return 0
    return limit_bytes


def ineligibility_reason(user, subscription, *, tariff=None, now: datetime | None = None) -> str | None:
    """Почему подписку НЕЛЬЗЯ перевести в Bypass-Off; ``None`` — можно.

    Платная (не триал, не суточная), живая по дате, в сквад тарифа входят
    обходы, у тарифа есть лимит трафика, владелец не заблокирован.
    """
    moment = now or datetime.now(UTC)
    if not is_configured():
        return 'not_configured'
    if user is None or getattr(user, 'status', UserStatus.ACTIVE.value) != UserStatus.ACTIVE.value:
        return 'user_inactive'
    if getattr(subscription, 'is_trial', False):
        return 'trial'
    if tariff is not None and getattr(tariff, 'is_daily', False):
        return 'daily'
    if getattr(subscription, 'status', None) not in _SUSPENDABLE_STATUSES:
        return 'status'
    end_date = getattr(subscription, 'end_date', None)
    if end_date is None:
        return 'expired'
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=UTC)
    if end_date <= moment:
        return 'expired'
    if settings.BYPASS_SQUAD_UUID not in (getattr(subscription, 'connected_squads', None) or []):
        return 'no_bypass_squad'
    if (getattr(subscription, 'traffic_limit_gb', 0) or 0) <= 0:
        return 'unlimited'
    return None


def is_suspended_snapshot(squads: Iterable[str]) -> bool:
    """Сквады из панели — это форма «обходы отключены», а не смена тарифа.

    Импорт из панели не должен переносить ``[Bypass-Off]`` в сквады подписки: в
    боте остаются сквады тарифа, к ним подписка и вернётся.
    """
    off = settings.BYPASS_OFF_SQUAD_UUID
    present = set(squads)
    if not off or off not in present:
        return False
    return present <= {off, settings.BYPASS_FALLBACK_SQUAD_UUID} - {''}
