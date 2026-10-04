"""Скидка «только на один тариф» (ULTIMA): не утекает на другие тарифы и покупки."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.utils.promo_offer import (
    get_user_active_promo_discount_percent,
    offer_discount_source,
    split_discount_source,
)


ULTIMA = 4


def _offer(offer_type='tariff_discount'):
    return SimpleNamespace(notification_type='promo_template_9', extra_data={'offer_type': offer_type})


def _user(source, percent=63):
    return SimpleNamespace(
        promo_offer_discount_percent=percent,
        promo_offer_discount_source=source,
        promo_offer_discount_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_source_carries_the_tariff(monkeypatch):
    monkeypatch.setattr(settings, 'PROMO_OFFER_TARIFF_ID', ULTIMA)
    source = offer_discount_source(_offer())
    assert source == 'tariff:4|promo_template_9'
    assert split_discount_source(source) == (4, 'promo_template_9')


def test_ordinary_offer_source_is_unchanged():
    assert offer_discount_source(_offer('purchase_discount')) == 'promo_template_9'
    assert split_discount_source('promo_template_9') == (None, 'promo_template_9')


def test_discount_only_for_its_tariff():
    user = _user('tariff:4|promo_template_9')
    assert get_user_active_promo_discount_percent(user, ULTIMA) == 63
    assert get_user_active_promo_discount_percent(user, 2) == 0  # другой тариф
    assert get_user_active_promo_discount_percent(user) == 0  # вызов без тарифа: безопасный отказ


def test_ordinary_discount_is_unaffected():
    user = _user('promo_template_3', percent=15)
    assert get_user_active_promo_discount_percent(user) == 15
    assert get_user_active_promo_discount_percent(user, 2) == 15


def test_expired_discount_is_zero():
    user = _user('tariff:4|promo_template_9')
    user.promo_offer_discount_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    assert get_user_active_promo_discount_percent(user, ULTIMA) == 0


# ───────────── цена через движок цен и страж вызовов ─────────────

import ast
import pathlib

from app.database.models import Tariff
from app.services.pricing_engine import pricing_engine


def _tariff(tariff_id, price_kopeks):
    return Tariff(
        id=tariff_id,
        name=f't{tariff_id}',
        period_prices={'2222': price_kopeks},
        device_limit=10,
        traffic_limit_gb=0,
        allowed_squads=[],
    )


def _engine_user(source, percent=37):
    user = _user(source, percent)
    user.promo_group = None
    user.promo_group_id = None
    user.get_primary_promo_group = lambda: None
    user.user_promo_groups = []
    return user


async def test_engine_discounts_ultima_only():
    user = _engine_user('tariff:4|promo_template_9')
    ultima = await pricing_engine.calculate_tariff_purchase_price(_tariff(4, 500_000), 2222, device_limit=10, user=user)
    other = await pricing_engine.calculate_tariff_purchase_price(_tariff(2, 15_900), 2222, device_limit=10, user=user)
    assert ultima.final_total == 315_000  # 5 000 ₽ → 3 150 ₽
    assert ultima.promo_offer_discount == 185_000
    assert other.promo_offer_discount == 0


async def test_engine_without_offer_has_no_discount():
    user = _engine_user(None, percent=0)
    result = await pricing_engine.calculate_tariff_purchase_price(_tariff(4, 500_000), 2222, device_limit=10, user=user)
    assert result.final_total == 500_000 and result.promo_offer_discount == 0


# Файлы, где процент скидки читают БЕЗ указания тарифа (получат 0 для тарифной скидки).
# Это режимы без тарифов (классика, суточные, подарки), мини-приложение и показ цен вне тарифов.
# Новый вызов без тарифа в коде покупки тарифов — повод остановиться и передать tariff.id.
# Движок цен: ровно один вызов без тарифа — классический режим (_calculate_classic_core).
_NO_TARIFF_ALLOWED_COUNT = {'app/services/pricing_engine.py': 1}
_NO_TARIFF_ALLOWED = {
    'app/cabinet/routes/gift.py',
    'app/handlers/menu.py',
    'app/handlers/simple_subscription.py',
    'app/handlers/subscription/common.py',
    'app/handlers/subscription/purchase.py',
    'app/services/subscription_auto_purchase_service.py',  # только суточный тариф
    'app/utils/price_display.py',
    'app/webapi/routes/miniapp.py',  # суточные тарифы и служебные места
}


def test_tariff_purchase_code_always_passes_the_tariff():
    root = pathlib.Path(__file__).resolve().parents[2]
    offenders = []
    for path in (root / 'app').rglob('*.py'):
        rel = path.relative_to(root).as_posix()
        if rel in _NO_TARIFF_ALLOWED or rel == 'app/utils/promo_offer.py':
            continue
        allowed_count = _NO_TARIFF_ALLOWED_COUNT.get(rel, 0)
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        found = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, 'id', getattr(node.func, 'attr', None))
                == 'get_user_active_promo_discount_percent'
                and len(node.args) + len(node.keywords) < 2
            ):
                found.append(f'{rel}:{node.lineno}')
        if len(found) > allowed_count:
            offenders.extend(found)
    assert not offenders, f'вызов без тарифа вне разрешённых файлов: {offenders}'
