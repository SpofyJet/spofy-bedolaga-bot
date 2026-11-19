from app.config import settings
from app.services.pricing_engine import pricing_engine
from app.utils.subscription_utils import (
    device_offer_counts,
    offers_device_choice,
    resolve_tariff_purchase_device_limit,
)


async def tariff_device_options(tariff, subscription, period_days: int, user) -> list[dict]:
    if not offers_device_choice(tariff, subscription, period_days):
        return []
    included = resolve_tariff_purchase_device_limit(tariff, subscription)
    maximum = tariff.max_device_limit or (settings.MAX_DEVICES_LIMIT if settings.MAX_DEVICES_LIMIT > 0 else 100)
    options = []
    for devices in [included, *device_offer_counts(included, maximum)]:
        price = await pricing_engine.calculate_tariff_purchase_price(
            tariff, period_days, device_limit=devices, custom_traffic_gb=None, user=user
        )
        options.append(
            {
                'devices': devices,
                'included': devices == included,
                'price_kopeks': price.final_total,
                'original_price_kopeks': price.original_total if price.original_total > price.final_total else None,
            }
        )
    return options
