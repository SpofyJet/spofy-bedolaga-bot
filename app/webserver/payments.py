from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
from collections.abc import AsyncIterator

import structlog
from aiogram import Bot
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import get_db
from app.external.pay2328 import Pay2328Service
from app.external.wata_webhook import WataWebhookHandler
from app.services.payment_service import PaymentService
from app.utils.webhook_client_ip import resolve_webhook_client_ip


logger = structlog.get_logger(__name__)


def _create_cors_response() -> Response:
    return Response(
        status_code=status.HTTP_200_OK,
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Crypto-Pay-API-Signature, Authorization',
        },
    )


def _resolve_proxied_client_ip(request: Request) -> str | None:
    """Адрес отправителя вебхука без доверия к клиентским заголовкам.

    Правила ``resolve_webhook_client_ip``: публичный peer — он и есть отправитель; за локальным/доверенным прокси читается только ``X-Forwarded-For``
    справа налево, ``X-Real-IP`` — лишь когда ``X-Forwarded-For`` нет; ``Cf-Connecting-Ip``
    — только от peer из сетей Cloudflare; неизвестный peer → ``None``.
    """
    client_ip = resolve_webhook_client_ip(
        request.client.host if request.client else None,
        forwarded_for=request.headers.get('x-forwarded-for'),
        real_ip=request.headers.get('x-real-ip'),
        cf_connecting_ip=request.headers.get('cf-connecting-ip'),
    )
    return str(client_ip) if client_ip is not None else None


# Bound concurrent payment-callback processing. Each callback holds a DB session
# for its whole processing duration (incl. external calls to the panel/provider).
# A burst of provider webhooks (e.g. a daily recurring-charge run firing 100+
# callbacks/min) would otherwise open a session per callback and exhaust the
# connection pool, starving the cabinet/admin API. Excess callbacks wait for a
# slot (without holding a DB connection); providers retry on timeout and
# processing is idempotent per order id.
_WEBHOOK_CALLBACK_CONCURRENCY = 16
_webhook_callback_semaphore: asyncio.Semaphore | None = None


def _get_webhook_callback_semaphore() -> asyncio.Semaphore:
    # Lazily created inside the running loop to avoid binding to the wrong loop.
    global _webhook_callback_semaphore
    if _webhook_callback_semaphore is None:
        _webhook_callback_semaphore = asyncio.Semaphore(_WEBHOOK_CALLBACK_CONCURRENCY)
    return _webhook_callback_semaphore


@contextlib.asynccontextmanager
async def _scoped_db() -> AsyncIterator[AsyncSession]:
    """Сессия ``get_db`` для вебхука: commit при успехе, rollback при исключении."""
    session_generator = get_db()
    session = await anext(session_generator)
    try:
        yield session
    except Exception as error:
        await session_generator.athrow(error)
        raise
    else:
        await anext(session_generator, None)


async def _process_payment_service_callback(
    payment_service: PaymentService,
    payload: dict,
    method_name: str,
) -> bool:
    async with _get_webhook_callback_semaphore():
        async with _scoped_db() as db:
            process_callback = getattr(payment_service, method_name)
            return await process_callback(db, payload)


def create_payment_router(bot: Bot, payment_service: PaymentService) -> APIRouter | None:
    """Роутер вебхуков платёжных провайдеров.

    Маршруты монтируются по ``is_X_configured()`` — по наличию учётных данных,
    а НЕ по флагу включения. Флаг переключают из админки в рантайме
    (``setattr(settings, ...)``), меню оплаты его перечитывает на каждой
    отрисовке, а маршруты FastAPI фиксируются один раз на старте процесса.
    Из-за этого провайдер, выключенный в момент перезапуска, после включения
    появлялся в меню и принимал оплату, но его вебхук отвечал 404: платёж
    проходил, зачисления не было и в логах бота не было ничего — запрос до
    него не доходил.

    Учётные данные при этом никуда не деваются, пока оператор щёлкает
    тумблером, так что маршрут остаётся живым. Побочно чинится и обратное:
    коллбек по платежу, начатому до выключения провайдера, теперь доезжает,
    а не теряется вместе с деньгами.
    """
    router = APIRouter()
    routes_registered = False

    if settings.is_cryptobot_configured():

        @router.options(settings.CRYPTOBOT_WEBHOOK_PATH)
        async def cryptobot_options() -> Response:
            return _create_cors_response()

        @router.post(settings.CRYPTOBOT_WEBHOOK_PATH)
        async def cryptobot_webhook(request: Request) -> JSONResponse:
            raw_body = await request.body()
            if not raw_body:
                return JSONResponse(
                    {'status': 'error', 'reason': 'empty_body'}, status_code=status.HTTP_400_BAD_REQUEST
                )

            payload_text = raw_body.decode('utf-8')
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_json'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            signature = request.headers.get('Crypto-Pay-API-Signature')
            logger.info(
                'CryptoBot webhook получен',
                update_type=payload.get('update_type') if isinstance(payload, dict) else None,
                has_signature=bool(signature),
                size=len(raw_body),
            )
            secret = settings.CRYPTOBOT_API_TOKEN
            if not secret:
                logger.error('CryptoBot webhook received but API token is not configured, rejecting')
                return JSONResponse(
                    {'status': 'error', 'reason': 'service_not_configured'},
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            if not signature:
                logger.warning('CryptoBot webhook отклонён: нет подписи')
                return JSONResponse(
                    {'status': 'error', 'reason': 'missing_signature'},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            from app.external.cryptobot import CryptoBotService

            if not CryptoBotService().verify_webhook_signature(payload_text, signature):
                logger.warning('CryptoBot webhook отклонён: подпись не совпала (проверьте токен приложения)')
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_signature'},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            try:
                success = await _process_payment_service_callback(
                    payment_service,
                    payload,
                    'process_cryptobot_webhook',
                )
                if success:
                    return JSONResponse({'status': 'ok'})

                logger.error(
                    'CryptoBot webhook processing failed',
                    payload=payload.get('payload', {}).get('invoice_id'),
                )
                return JSONResponse(
                    {'status': 'error', 'reason': 'processing_failed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception('CryptoBot webhook processing error', e=e)
                return JSONResponse(
                    {'status': 'error', 'reason': 'processing_failed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        routes_registered = True

    if settings.is_xrocket_configured():

        @router.options(settings.XROCKET_WEBHOOK_PATH)
        async def xrocket_options() -> Response:
            return _create_cors_response()

        @router.post(settings.XROCKET_WEBHOOK_PATH)
        async def xrocket_webhook(request: Request) -> JSONResponse:
            raw_body = await request.body()
            if not raw_body:
                return JSONResponse(
                    {'status': 'error', 'reason': 'empty_body'}, status_code=status.HTTP_400_BAD_REQUEST
                )

            payload_text = raw_body.decode('utf-8')
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_json'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Pay API: Signature + Signature-Timestamp, ключ — XROCKET_WEBHOOK_SECRET.
            # Без секрета отвечаем 503: xRocket повторит, а оплату за ~15 с проведёт автопроверка счетов.
            if not (settings.XROCKET_WEBHOOK_SECRET or '').strip():
                logger.warning('xRocket webhook получен, но XROCKET_WEBHOOK_SECRET не задан')
                return JSONResponse(
                    {'status': 'error', 'reason': 'service_not_configured'},
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            signature = request.headers.get('signature')
            timestamp = request.headers.get('signature-timestamp')
            if not signature or not timestamp:
                return JSONResponse(
                    {'status': 'error', 'reason': 'missing_signature'},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            from app.external.xrocket import XRocketService

            if not XRocketService().verify_webhook_signature(
                raw_body, signature, timestamp, request.headers.get('signature-version') or 'v1'
            ):
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_signature'},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            payload = XRocketService.to_legacy_webhook(payload)

            try:
                success = await _process_payment_service_callback(
                    payment_service,
                    payload,
                    'process_xrocket_webhook',
                )
                if success:
                    return JSONResponse({'status': 'ok'})

                logger.error(
                    'xRocket webhook processing failed',
                    invoice_id=(payload.get('data') or {}).get('id'),
                )
                return JSONResponse(
                    {'status': 'error', 'reason': 'processing_failed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception('xRocket webhook processing error', e=e)
                return JSONResponse(
                    {'status': 'error', 'reason': 'processing_failed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        routes_registered = True

    if settings.is_wata_configured():
        wata_handler = WataWebhookHandler(payment_service)

        @router.options(settings.WATA_WEBHOOK_PATH)
        async def wata_options() -> Response:
            return Response(
                status_code=status.HTTP_200_OK,
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, X-Signature',
                },
            )

        @router.get(settings.WATA_WEBHOOK_PATH)
        async def wata_health() -> JSONResponse:
            return JSONResponse(
                {
                    'status': 'ok',
                    'service': 'wata_webhook',
                    'enabled': settings.is_wata_enabled(),
                }
            )

        @router.post(settings.WATA_WEBHOOK_PATH)
        async def wata_webhook(request: Request) -> JSONResponse:
            raw_body = await request.body()
            if not raw_body:
                return JSONResponse(
                    {'status': 'error', 'reason': 'empty_body'}, status_code=status.HTTP_400_BAD_REQUEST
                )

            signature = request.headers.get('X-Signature') or ''
            if not await wata_handler._verify_signature(raw_body.decode('utf-8'), signature):  # type: ignore[attr-defined]
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_signature'},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            try:
                payload = json.loads(raw_body.decode('utf-8'))
            except json.JSONDecodeError:
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_json'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            try:
                success = await _process_payment_service_callback(
                    payment_service,
                    payload,
                    'process_wata_webhook',
                )
                if success:
                    return JSONResponse({'status': 'ok'})

                order_id = payload.get('orderId') or payload.get('order_id') or 'unknown'
                logger.error('Wata webhook processing failed', order_id=order_id, payload=payload)
                return JSONResponse(
                    {'status': 'error', 'reason': 'not_processed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception('Wata webhook processing error', e=e)
                return JSONResponse(
                    {'status': 'error', 'reason': 'not_processed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        routes_registered = True

    if settings.is_pay2328_configured():
        pay2328_service = Pay2328Service()

        @router.options(settings.PAY2328_WEBHOOK_PATH)
        async def pay2328_options() -> Response:
            return Response(
                status_code=status.HTTP_200_OK,
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                },
            )

        @router.get(settings.PAY2328_WEBHOOK_PATH)
        async def pay2328_health() -> JSONResponse:
            return JSONResponse(
                {
                    'status': 'ok',
                    'service': 'pay2328_webhook',
                    'enabled': settings.is_pay2328_enabled(),
                }
            )

        @router.post(settings.PAY2328_WEBHOOK_PATH)
        async def pay2328_webhook(request: Request) -> JSONResponse:
            try:
                payload = await request.json()
            except json.JSONDecodeError:
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_json'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            if not pay2328_service.verify_webhook_signature(payload):
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_signature'},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            try:
                success = await _process_payment_service_callback(
                    payment_service,
                    payload,
                    'process_pay2328_webhook',
                )
                if success:
                    return JSONResponse({'status': 'ok'})

                uuid_val = payload.get('uuid', 'unknown')
                logger.error('2328.io webhook processing failed', uuid_val=uuid_val)
                return JSONResponse(
                    {'status': 'error', 'reason': 'not_processed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception('2328.io webhook processing error', e=e)
                return JSONResponse(
                    {'status': 'error', 'reason': 'not_processed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        routes_registered = True

    if settings.is_platega_configured():

        @router.get(settings.PLATEGA_WEBHOOK_PATH)
        async def platega_health() -> JSONResponse:
            return JSONResponse(
                {
                    'status': 'ok',
                    'service': 'platega_webhook',
                    'enabled': settings.is_platega_enabled(),
                }
            )

        @router.post(settings.PLATEGA_WEBHOOK_PATH)
        async def platega_webhook(request: Request) -> JSONResponse:
            merchant_id = request.headers.get('X-MerchantId', '')
            secret = request.headers.get('X-Secret', '')
            raw_body = await request.body()
            if not merchant_id and not secret and not raw_body.strip():
                logger.info('Platega webhook verification ping (no auth headers, empty body)')
                return JSONResponse({'status': 'ok'})
            if not (
                hmac.compare_digest(merchant_id, settings.PLATEGA_MERCHANT_ID or '')
                and hmac.compare_digest(secret, settings.PLATEGA_SECRET or '')
            ):
                return JSONResponse(
                    {'status': 'error', 'reason': 'unauthorized'},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

            try:
                payload = await request.json()
            except json.JSONDecodeError:
                return JSONResponse(
                    {'status': 'error', 'reason': 'invalid_json'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # Platega sends both one-off payment callbacks and recurring СБП-subscription
            # callbacks (charge + status-change) to this same endpoint. Subscription
            # payloads carry paymentMethod 6, a subscriptionId, or a SUBSCRIPTION_-prefixed
            # status — matched case-insensitively, because the live charge callback
            # arrives in camelCase while the spec examples are PascalCase.
            from app.services.platega_recurrent import is_subscription_callback

            is_subscription = is_subscription_callback(payload)

            try:
                if is_subscription:
                    # process_platega_subscription_callback self-handles errors/logging
                    # and always returns None — it is NOT a success flag like the other
                    # handlers, so the response must not be gated on its return value.
                    # Per spec, subscription callbacks always get HTTP 200 unless
                    # dispatch itself raises (caught below → 400, Platega retries).
                    await _process_payment_service_callback(
                        payment_service,
                        payload,
                        'process_platega_subscription_callback',
                    )
                    return JSONResponse({'status': 'ok'})

                success = await _process_payment_service_callback(
                    payment_service,
                    payload,
                    'process_platega_webhook',
                )
                if success:
                    return JSONResponse({'status': 'ok'})

                transaction_id = (
                    payload.get('id') or payload.get('transactionId') or payload.get('transaction_id') or 'unknown'
                )
                # Ключи (не значения) в логе: по ним видно, в какой форме пришёл
                # коллбек, если он снова не совпадёт с ожидаемой.
                logger.error(
                    'Platega webhook processing failed',
                    transaction_id=transaction_id,
                    payload_keys=sorted(payload) if isinstance(payload, dict) else None,
                )
                return JSONResponse(
                    {'status': 'error', 'reason': 'not_processed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception('Platega webhook processing error', e=e)
                return JSONResponse(
                    {'status': 'error', 'reason': 'not_processed'},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        routes_registered = True

    if routes_registered:

        @router.get('/health/payment-webhooks')
        async def payment_webhooks_health() -> JSONResponse:
            return JSONResponse(
                {
                    'status': 'ok',
                    'cryptobot_enabled': settings.is_cryptobot_enabled(),
                    'xrocket_enabled': settings.is_xrocket_enabled(),
                    'wata_enabled': settings.is_wata_enabled(),
                    'pay2328_enabled': settings.is_pay2328_enabled(),
                    'platega_enabled': settings.is_platega_enabled(),
                }
            )

    return router if routes_registered else None
