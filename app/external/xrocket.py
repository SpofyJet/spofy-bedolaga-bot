import hashlib
import hmac
import os
import time
from decimal import Decimal
from typing import Any

import aiohttp
import structlog

from app.config import settings


logger = structlog.get_logger(__name__)


class XRocketService:
    """Клиент xRocket Pay API (https://pay.api.xrocket.exchange, пути /api/v1/…).

    Авторизация: ``Authorization: Bearer <токен приложения>``.
    Ответ — сам объект без обёртки ``success/data``; ошибки — RFC 9457 (поле ``type``).
    Суммы — десятичные строки. Наружу клиент отдаёт счета в прежнем (Legacy) виде:
    ``id``, ``status``, ``link``, ``paid``, ``payload`` — остальной код не меняется.
    """

    # Без таймаута зависший ответ xRocket держал вебхук/кнопку «Проверить статус»
    # и цикл автопроверки сколько угодно долго (дефолт aiohttp — 5 минут).
    REQUEST_TIMEOUT_SECONDS = 20

    def __init__(self):
        self.api_token = settings.XROCKET_API_TOKEN
        self.base_url = settings.get_xrocket_base_url().rstrip('/')

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        *,
        auth: bool = True,
        not_found: Any | None = None,
    ) -> Any | None:
        if auth and not self.api_token:
            logger.error('xRocket API token не настроен')
            return None

        url = f'{self.base_url}/{endpoint.lstrip("/")}'
        headers = {'Accept': 'application/json'}
        if auth:
            headers['Authorization'] = f'Bearer {self.api_token}'

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT_SECONDS)
            ) as session:
                request_kwargs: dict[str, Any] = {'headers': headers}

                if method.upper() in ('GET', 'DELETE'):
                    if data:
                        request_kwargs['params'] = data
                elif data is not None:
                    request_kwargs['json'] = data

                async with session.request(method, url, **request_kwargs) as response:
                    if response.status == 404 and not_found is not None:
                        logger.info('xRocket API: объект не найден', endpoint=endpoint)
                        return not_found

                    try:
                        response_data = await response.json(content_type=None)
                    except ValueError:
                        logger.warning('xRocket API ответил не JSON', status=response.status, endpoint=endpoint)
                        return None

                    if 200 <= response.status < 300:
                        return response_data

                    logger.error(
                        'xRocket API ошибка',
                        status=response.status,
                        endpoint=endpoint,
                        response_data=response_data,
                    )
                    return None

        except Exception as e:
            logger.error('Ошибка запроса к xRocket API', error=e)
            return None

    @staticmethod
    def _legacy_invoice(invoice: dict[str, Any]) -> dict[str, Any]:
        """Счёт Pay API → поля, которые ждёт платёжный сервис (как в Legacy API)."""
        links = invoice.get('links') or {}
        callback = invoice.get('callback') or {}
        cb_payload = callback.get('payload')
        payload = cb_payload.get('payload') if isinstance(cb_payload, dict) else None
        return {
            **invoice,
            'id': invoice.get('id'),
            'status': invoice.get('status'),
            'amount': invoice.get('priceAmount'),
            'currency': invoice.get('priceCurrency'),
            'link': links.get('telegramBotLink') or links.get('webLink') or links.get('telegramMiniAppLink'),
            'payload': payload,
            'paid': None,
        }

    async def create_invoice(
        self,
        amount: float,
        currency: str = 'USDT',
        description: str | None = None,
        payload: str | None = None,
        expires_in: int | None = None,
        callback_url: str | None = None,
    ) -> dict[str, Any] | None:
        data: dict[str, Any] = {
            'priceAmount': format(Decimal(str(round(float(amount), 9))).normalize(), 'f'),
            'priceCurrency': currency,
            'payCurrencies': [currency],
            'numPayments': 1,
        }

        if description:
            data['description'] = description[:1000]

        callback: dict[str, Any] = {}
        if payload and len(payload.encode()) < 3500:
            callback['payload'] = {'payload': payload}
        if callback_url:
            callback['callbackUrl'] = callback_url
        if callback:
            data['callback'] = callback

        if expires_in:
            # Pay API: время жизни в миллисекундах; держим прежний максимум — сутки
            data['expiresIn'] = min(int(expires_in), 86400) * 1000

        result = await self._make_request('POST', 'api/v1/invoices', data)
        if not isinstance(result, dict) or not result.get('id'):
            return None

        logger.info('Создан xRocket invoice', invoice_id=result.get('id'), amount=amount, currency=currency)
        return self._legacy_invoice(result)

    async def get_invoice(self, invoice_id: str | int) -> dict[str, Any] | None:
        """Счёт по id. Удалённый счёт (404) возвращается как истёкший."""
        result = await self._make_request(
            'GET',
            'api/v1/invoice',
            {'invoiceId': str(invoice_id)},
            not_found={'id': invoice_id, 'status': 'expired'},
        )
        if not isinstance(result, dict):
            return None
        return self._legacy_invoice(result)

    async def get_fiat_rate(self, crypto: str, fiat: str = 'RUB') -> float | None:
        """Курс 1 {crypto} = N {fiat}.

        Цепочка источников:
        1) Pay API xRocket GET /api/v1/rates (публичный, без токена);
        2) CryptoBot getExchangeRates — токен уже настроен в боте;
        3) статический резерв из env XROCKET_FALLBACK_USDT_RUB (только USDT/RUB).

        Сбои отдельных источников — warning (без репорта в админку); error —
        только когда недоступны ВСЕ источники (платёж будет отменён).
        """
        rate = await self._get_rate_pay_api(crypto, fiat)
        if rate:
            return rate

        rate = await self._get_rate_cryptobot(crypto, fiat)
        if rate:
            return rate

        if crypto.upper() == 'USDT' and fiat.upper() == 'RUB':
            fallback = (os.environ.get('XROCKET_FALLBACK_USDT_RUB') or '').strip()
            if fallback:
                try:
                    value = float(fallback.replace(',', '.'))
                    if value > 0:
                        logger.warning(
                            'xRocket: используется статический курс из XROCKET_FALLBACK_USDT_RUB',
                            rate=value,
                        )
                        return value
                except ValueError:
                    logger.warning('xRocket: некорректный XROCKET_FALLBACK_USDT_RUB', value=fallback)

        logger.error(
            'xRocket: курс недоступен из всех источников — платёж будет отменён',
            crypto=crypto,
            fiat=fiat,
        )
        return None

    async def _get_rate_pay_api(self, crypto: str, fiat: str) -> float | None:
        """Курс 1 {crypto} в {fiat} из Pay API xRocket (тот же, по которому xRocket считает счета)."""
        result = await self._make_request(
            'GET', 'api/v1/rates', {'base': fiat.upper(), 'assets': crypto.upper()}, auth=False
        )
        if not isinstance(result, list):
            logger.warning('xRocket: курс из Pay API не получен', crypto=crypto, fiat=fiat)
            return None
        for item in result:
            if str(item.get('currency', '')).upper() == crypto.upper():
                try:
                    rate = float(item.get('rate') or 0)
                except (TypeError, ValueError):
                    rate = 0
                if rate > 0:
                    return rate
        return None

    async def _get_rate_cryptobot(self, crypto: str, fiat: str) -> float | None:
        """Резервный курс через CryptoBot getExchangeRates (токен уже есть в настройках)."""
        try:
            from app.external.cryptobot import CryptoBotService

            service = CryptoBotService()
            if not getattr(service, 'api_token', None):
                logger.warning('xRocket: CryptoBot токен не настроен — резервный курс недоступен')
                return None
            rates = await service.get_exchange_rates()
            if not rates:
                logger.warning('xRocket: CryptoBot getExchangeRates не вернул данные')
                return None
            source = 'TON' if crypto.upper() in ('GRAM', 'TONCOIN') else crypto.upper()
            for item in rates:
                if (
                    str(item.get('source', '')).upper() == source
                    and str(item.get('target', '')).upper() == fiat.upper()
                    and item.get('is_valid', True)
                ):
                    rate = float(item.get('rate') or 0)
                    if rate > 0:
                        logger.info(
                            'xRocket: курс получен через CryptoBot-резерв',
                            crypto=crypto,
                            fiat=fiat,
                            rate=rate,
                        )
                        return rate
            logger.warning('xRocket: в CryptoBot нет нужной пары', crypto=crypto, fiat=fiat)
            return None
        except Exception as e:
            logger.warning('xRocket: ошибка CryptoBot-резерва курса', crypto=crypto, fiat=fiat, error=str(e))
            return None

    async def get_min_invoice(self, currency: str) -> float | None:
        """В Pay API минимума счёта нет в справочнике: слишком малую сумму xRocket отклонит сам."""
        return None

    def verify_webhook_signature(self, body: bytes | str, signature: str, timestamp: str, version: str = 'v1') -> bool:
        """Pay API: hex HMAC-SHA256(webhook secret, f"{Signature-Timestamp}.{raw_body}"), окно 5 минут."""
        secret = (settings.XROCKET_WEBHOOK_SECRET or '').strip()
        if not secret:
            logger.error('xRocket: XROCKET_WEBHOOK_SECRET не задан, вебхук отклонён (оплату проведёт автопроверка)')
            return False
        if not signature or not timestamp or (version or 'v1') != 'v1':
            return False
        ts = timestamp.strip()
        if not ts.isdigit() or abs(time.time() * 1000 - int(ts)) > 5 * 60 * 1000:
            logger.warning('xRocket webhook: устаревшая или неверная метка времени', timestamp=ts)
            return False
        raw = body.encode('utf-8') if isinstance(body, str) else body
        expected = hmac.new(secret.encode(), ts.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        if hmac.compare_digest(signature.strip().lower(), expected):
            return True
        logger.error('Неверная подпись xRocket webhook', body_length=len(raw))
        return False

    @staticmethod
    def to_legacy_webhook(webhook_data: dict[str, Any]) -> dict[str, Any]:
        """Вебхук Pay API → прежний вид {'type': 'invoicePay', 'data': {...}} для платёжного сервиса.

        Оплату проводим по invoice_status_changed со статусом paid (счёт на один платёж);
        остальные события пропускаются как «не оплачено».
        """
        if webhook_data.get('type') != 'invoice':
            return webhook_data
        data = webhook_data.get('data') or {}
        invoice = data.get('invoice') or {}
        event = data.get('event')
        legacy = XRocketService._legacy_invoice(invoice)
        if event == 'payment_status_changed':
            payment = data.get('payment') or {}
            if payment.get('status') == 'paid' and payment.get('finalizedAt'):
                legacy['status'] = 'paid'
                legacy['paid'] = payment.get('finalizedAt')
        elif event != 'invoice_status_changed':
            legacy['status'] = 'unknown_event'
        return {'type': 'invoicePay', 'data': legacy}

    async def process_webhook(self, webhook_data: dict[str, Any]) -> dict[str, Any] | None:
        try:
            update_type = webhook_data.get('type')

            if update_type == 'invoicePay':
                invoice_data = webhook_data.get('data', {}) or {}
                payment = invoice_data.get('payment', {}) or {}

                return {
                    'event_type': 'payment',
                    'payment_id': str(invoice_data.get('id')),
                    'amount': invoice_data.get('amount'),
                    'asset': invoice_data.get('currency'),
                    'status': invoice_data.get('status'),
                    'user_payload': invoice_data.get('payload'),
                    'paid_at': invoice_data.get('paid') or payment.get('paid'),
                    'payment_system': 'xrocket',
                }

            logger.warning('Неизвестный тип xRocket webhook', update_type=update_type)
            return None

        except Exception as e:
            logger.error('Ошибка обработки xRocket webhook', error=e)
            return None
