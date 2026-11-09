"""Агрегирующий сервис, собирающий все платёжные модули."""

from __future__ import annotations

import json
from importlib import import_module
from typing import Any

import structlog
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.external.cryptobot import CryptoBotService
from app.external.heleket import HeleketService
from app.external.telegram_stars import TelegramStarsService
from app.external.xrocket import XRocketService
from app.services.payment import (
    CryptoBotPaymentMixin,
    HeleketPaymentMixin,
    PaymentCommonMixin,
    PlategaPaymentMixin,
    TelegramStarsMixin,
    WataPaymentMixin,
    XRocketPaymentMixin,
)
from app.services.payment.payer_identity import resolve_guest_payer
from app.services.platega_service import PlategaService
from app.services.wata_service import WataService
from app.utils.currency_converter import currency_converter


logger = structlog.get_logger(__name__)


# --- Совместимость: экспортируем функции, которые активно мокаются в тестах ---


async def create_transaction(*args, **kwargs):
    transaction_crud = import_module('app.database.crud.transaction')
    return await transaction_crud.create_transaction(*args, **kwargs)


async def get_transaction_by_external_id(*args, **kwargs):
    transaction_crud = import_module('app.database.crud.transaction')
    return await transaction_crud.get_transaction_by_external_id(*args, **kwargs)


async def add_user_balance(*args, **kwargs):
    user_crud = import_module('app.database.crud.user')
    return await user_crud.add_user_balance(*args, **kwargs)


async def get_user_by_id(*args, **kwargs):
    user_crud = import_module('app.database.crud.user')
    return await user_crud.get_user_by_id(*args, **kwargs)


async def get_user_by_telegram_id(*args, **kwargs):
    user_crud = import_module('app.database.crud.user')
    return await user_crud.get_user_by_telegram_id(*args, **kwargs)


async def create_wata_payment(*args, **kwargs):
    wata_crud = import_module('app.database.crud.wata')
    return await wata_crud.create_wata_payment(*args, **kwargs)


async def get_wata_payment_by_link_id(*args, **kwargs):
    wata_crud = import_module('app.database.crud.wata')
    return await wata_crud.get_wata_payment_by_link_id(*args, **kwargs)


async def get_wata_payment_by_id(*args, **kwargs):
    wata_crud = import_module('app.database.crud.wata')
    return await wata_crud.get_wata_payment_by_id(*args, **kwargs)


# Алиас для совместимости с хендлерами
async def get_wata_payment_by_local_id(*args, **kwargs):
    return await get_wata_payment_by_id(*args, **kwargs)


async def get_wata_payment_by_order_id(*args, **kwargs):
    wata_crud = import_module('app.database.crud.wata')
    return await wata_crud.get_wata_payment_by_order_id(*args, **kwargs)


async def update_wata_payment_status(*args, **kwargs):
    wata_crud = import_module('app.database.crud.wata')
    return await wata_crud.update_wata_payment_status(*args, **kwargs)


async def link_wata_payment_to_transaction(*args, **kwargs):
    wata_crud = import_module('app.database.crud.wata')
    return await wata_crud.link_wata_payment_to_transaction(*args, **kwargs)


async def create_platega_payment(*args, **kwargs):
    platega_crud = import_module('app.database.crud.platega')
    return await platega_crud.create_platega_payment(*args, **kwargs)


async def get_platega_payment_by_id(*args, **kwargs):
    platega_crud = import_module('app.database.crud.platega')
    return await platega_crud.get_platega_payment_by_id(*args, **kwargs)


async def get_platega_payment_by_id_for_update(*args, **kwargs):
    platega_crud = import_module('app.database.crud.platega')
    return await platega_crud.get_platega_payment_by_id_for_update(*args, **kwargs)


async def get_platega_payment_by_transaction_id(*args, **kwargs):
    platega_crud = import_module('app.database.crud.platega')
    return await platega_crud.get_platega_payment_by_transaction_id(*args, **kwargs)


async def get_platega_payment_by_correlation_id(*args, **kwargs):
    platega_crud = import_module('app.database.crud.platega')
    return await platega_crud.get_platega_payment_by_correlation_id(*args, **kwargs)


async def update_platega_payment(*args, **kwargs):
    platega_crud = import_module('app.database.crud.platega')
    return await platega_crud.update_platega_payment(*args, **kwargs)


async def link_platega_payment_to_transaction(*args, **kwargs):
    platega_crud = import_module('app.database.crud.platega')
    return await platega_crud.link_platega_payment_to_transaction(*args, **kwargs)


async def create_cryptobot_payment(*args, **kwargs):
    crypto_crud = import_module('app.database.crud.cryptobot')
    return await crypto_crud.create_cryptobot_payment(*args, **kwargs)


async def get_cryptobot_payment_by_invoice_id(*args, **kwargs):
    crypto_crud = import_module('app.database.crud.cryptobot')
    return await crypto_crud.get_cryptobot_payment_by_invoice_id(*args, **kwargs)


async def update_cryptobot_payment_status(*args, **kwargs):
    crypto_crud = import_module('app.database.crud.cryptobot')
    return await crypto_crud.update_cryptobot_payment_status(*args, **kwargs)


async def link_cryptobot_payment_to_transaction(*args, **kwargs):
    crypto_crud = import_module('app.database.crud.cryptobot')
    return await crypto_crud.link_cryptobot_payment_to_transaction(*args, **kwargs)


async def create_xrocket_payment(*args, **kwargs):
    xr_crud = import_module('app.database.crud.xrocket')
    return await xr_crud.create_xrocket_payment(*args, **kwargs)


async def get_xrocket_payment_by_invoice_id(*args, **kwargs):
    xr_crud = import_module('app.database.crud.xrocket')
    return await xr_crud.get_xrocket_payment_by_invoice_id(*args, **kwargs)


async def update_xrocket_payment_status(*args, **kwargs):
    xr_crud = import_module('app.database.crud.xrocket')
    return await xr_crud.update_xrocket_payment_status(*args, **kwargs)


async def link_xrocket_payment_to_transaction(*args, **kwargs):
    xr_crud = import_module('app.database.crud.xrocket')
    return await xr_crud.link_xrocket_payment_to_transaction(*args, **kwargs)


async def create_heleket_payment(*args, **kwargs):
    heleket_crud = import_module('app.database.crud.heleket')
    return await heleket_crud.create_heleket_payment(*args, **kwargs)


async def get_heleket_payment_by_uuid(*args, **kwargs):
    heleket_crud = import_module('app.database.crud.heleket')
    return await heleket_crud.get_heleket_payment_by_uuid(*args, **kwargs)


async def get_heleket_payment_by_id(*args, **kwargs):
    heleket_crud = import_module('app.database.crud.heleket')
    return await heleket_crud.get_heleket_payment_by_id(*args, **kwargs)


async def update_heleket_payment(*args, **kwargs):
    heleket_crud = import_module('app.database.crud.heleket')
    return await heleket_crud.update_heleket_payment(*args, **kwargs)


async def link_heleket_payment_to_transaction(*args, **kwargs):
    heleket_crud = import_module('app.database.crud.heleket')
    return await heleket_crud.link_heleket_payment_to_transaction(*args, **kwargs)


class PaymentService(
    PaymentCommonMixin,
    TelegramStarsMixin,
    CryptoBotPaymentMixin,
    XRocketPaymentMixin,
    HeleketPaymentMixin,
    PlategaPaymentMixin,
    WataPaymentMixin,
):
    """Основной интерфейс платежей, делегирующий работу специализированным mixin-ам."""

    def __init__(self, bot: Bot | None = None) -> None:
        # Бот нужен для отправки уведомлений и создания звёздных инвойсов.
        self.bot = bot
        self.stars_service = TelegramStarsService(bot) if bot else None
        self.cryptobot_service = CryptoBotService() if settings.is_cryptobot_enabled() else None
        self.xrocket_service = XRocketService() if settings.is_xrocket_enabled() else None
        self.heleket_service = HeleketService() if settings.is_heleket_enabled() else None
        self.platega_service = PlategaService() if settings.is_platega_enabled() else None
        self.wata_service = WataService() if settings.is_wata_enabled() else None

    # ------------------------------------------------------------------
    # Guest (landing page) payments
    # ------------------------------------------------------------------
    # Supported providers for guest payments (to be extended per-provider):
    #   - cryptobot
    #   - heleket
    #   - platega
    #   - wata
    #   - telegram_stars
    # Each provider returns a different result dict; the caller must
    # extract the payment URL from the provider-specific key.
    # ------------------------------------------------------------------

    async def create_guest_payment(
        self,
        db: AsyncSession,
        *,
        amount_kopeks: int,
        payment_method: str,
        description: str,
        purchase_token: str,
        return_url: str,
    ) -> dict[str, Any] | None:
        """Create a payment for a guest (unauthenticated) landing-page purchase.

        Stores ``purchase_token`` in payment metadata so that webhook handlers
        can match the completed payment back to the corresponding
        :class:`GuestPurchase` record.

        Returns a provider-specific dict with at least ``payment_url`` on
        success, or ``None`` when the requested provider is unavailable or
        the creation call fails.
        """
        guest_metadata: dict[str, Any] = {
            'purpose': 'guest_purchase',
            'purchase_token': purchase_token,
            'source': 'landing',
        }

        async def _patch_guest_metadata(local_payment_id: int, model_name: str) -> None:
            """Merge guest_metadata into the local payment record's metadata_json."""
            try:
                crud_module = import_module(f'app.database.crud.{model_name}')
                getter_name = f'get_{model_name}_payment_by_id'
                getter = getattr(crud_module, getter_name, None)
                if getter is None:
                    logger.warning(
                        'No getter found for patching guest metadata', model_name=model_name, getter_name=getter_name
                    )
                    return
                payment_record = await getter(db, local_payment_id)
                if payment_record is None:
                    return
                existing_meta = dict(getattr(payment_record, 'metadata_json', None) or {})
                existing_meta.update(guest_metadata)
                payment_record.metadata_json = existing_meta
                await db.commit()
            except Exception as patch_error:
                logger.warning(
                    'Failed to patch guest metadata into payment record',
                    model_name=model_name,
                    local_payment_id=local_payment_id,
                    error=patch_error,
                )

        # --- CryptoBot --------------------------------------------------------
        if payment_method == 'cryptobot':
            if self.cryptobot_service is None:
                logger.warning('CryptoBot is not enabled, cannot create guest payment')
                return None

            amount_rubles = amount_kopeks / 100
            try:
                amount_usd = await currency_converter.rub_to_usd(amount_rubles)
            except Exception as conv_error:
                logger.error('Currency conversion failed for CryptoBot guest payment', error=conv_error)
                return None

            # Encode guest metadata into the payload string (CryptoBot uses payload, not metadata dict)
            payload_str = json.dumps(guest_metadata, ensure_ascii=False)

            result = await self.create_cryptobot_payment(
                db=db,
                user_id=None,
                amount_usd=amount_usd,
                asset='USDT',
                description=description,
                payload=payload_str,
            )
            if result:
                # CryptoBot stores guest_metadata in the payload field (no metadata_json column)
                payment_url = result.get('bot_invoice_url') or result.get('mini_app_invoice_url')
                return {
                    'payment_url': payment_url,
                    'payment_id': result.get('invoice_id'),
                    'provider': 'cryptobot',
                }
            return None

        # --- Heleket ----------------------------------------------------------
        if payment_method == 'heleket':
            if self.heleket_service is None:
                logger.warning('Heleket is not enabled, cannot create guest payment')
                return None

            result = await self.create_heleket_payment(
                db=db,
                user_id=None,
                amount_kopeks=amount_kopeks,
                description=description,
                return_url=return_url,
            )
            if result:
                await _patch_guest_metadata(result['local_payment_id'], 'heleket')
                return {
                    'payment_url': result.get('payment_url'),
                    'payment_id': result.get('uuid'),
                    'provider': 'heleket',
                }
            return None

        # --- Platega ----------------------------------------------------------
        if payment_method.startswith('platega'):
            if self.platega_service is None:
                logger.warning('Platega is not enabled, cannot create guest payment')
                return None

            # Extract method code: "platega_2" -> 2, "platega" -> first active method
            method_code: int | None = None
            if '_' in payment_method:
                suffix = payment_method.split('_', 1)[1]
                try:
                    method_code = int(suffix)
                except ValueError:
                    pass

            if method_code is None:
                active_methods = settings.get_platega_active_methods()
                method_code = active_methods[0] if active_methods else 2

            result = await self.create_platega_payment(
                db=db,
                user_id=None,
                amount_kopeks=amount_kopeks,
                description=description,
                language=settings.DEFAULT_LANGUAGE,
                payment_method_code=method_code,
                return_url=return_url,
                payer=await resolve_guest_payer(db, purchase_token),
            )
            if result:
                await _patch_guest_metadata(result['local_payment_id'], 'platega')
                return {
                    'payment_url': result.get('redirect_url'),
                    'payment_id': result.get('correlation_id'),
                    'provider': 'platega',
                }
            return None

        # --- WATA -------------------------------------------------------------
        if payment_method == 'wata':
            if self.wata_service is None:
                logger.warning('WATA is not enabled, cannot create guest payment')
                return None

            result = await self.create_wata_payment(
                db=db,
                user_id=None,
                amount_kopeks=amount_kopeks,
                description=description,
                return_url=return_url,
            )
            if result:
                await _patch_guest_metadata(result['local_payment_id'], 'wata')
                return {
                    'payment_url': result.get('payment_url'),
                    'payment_id': result.get('payment_link_id'),
                    'provider': 'wata',
                }
            return None

        # --- Telegram Stars ---------------------------------------------------
        if payment_method == 'telegram_stars':
            if not settings.TELEGRAM_STARS_ENABLED:
                logger.warning('Telegram Stars is not enabled, cannot create guest payment')
                return None

            if self.bot is None:
                logger.warning('Bot instance required for Stars guest payment')
                return None

            from aiogram.types import LabeledPrice

            rate = settings.get_stars_rate()
            if rate <= 0:
                logger.error('TELEGRAM_STARS_RATE_RUB is not positive, cannot create Stars invoice')
                return None

            amount_rubles = amount_kopeks / 100
            stars_amount = max(1, round(amount_rubles / rate))

            payload = f'guest_purchase_{purchase_token}'

            try:
                invoice_url = await self.bot.create_invoice_link(
                    title='Подарочная подписка VPN',
                    description=f'{description} ({stars_amount} ⭐)',
                    payload=payload,
                    provider_token='',
                    currency='XTR',
                    prices=[LabeledPrice(label='Подарочная подписка', amount=stars_amount)],
                )

                logger.info(
                    'Created Stars invoice for guest purchase',
                    stars_amount=stars_amount,
                    token_length=len(purchase_token),
                )
                return {
                    'payment_url': invoice_url,
                    'payment_id': f'stars_{purchase_token[:12]}',
                    'provider': 'telegram_stars',
                }

            except Exception as stars_error:
                logger.error('Error creating Stars invoice for guest payment', error=stars_error)
                return None

        # --- Unsupported provider ---------------------------------------------
        logger.warning(
            'Guest payment requested for unsupported provider',
            payment_method=payment_method,
            token_length=len(purchase_token),
        )
        return None
