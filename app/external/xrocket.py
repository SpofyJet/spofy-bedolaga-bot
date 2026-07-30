import hashlib
import hmac
import json
import os
from typing import Any

import aiohttp
import structlog

from app.config import settings


logger = structlog.get_logger(__name__)


class XRocketService:
    """Клиент xRocket Pay API (https://pay.xrocket.tg/api-json).

    Авторизация: header ``Rocket-Pay-Key``.
    Ответы обёрнуты в ``{"success": bool, "data": {...}}``.
    """

    # Публичный Trade API (курсы), авторизация не нужна
    TRADE_URL = 'https://trade.xrocket.exchange'

    def __init__(self):
        self.api_token = settings.XROCKET_API_TOKEN
        self.base_url = settings.get_xrocket_base_url().rstrip('/')

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
    ) -> Any | None:
        if not self.api_token:
            logger.error('xRocket API token не настроен')
            return None

        url = f'{self.base_url}/{endpoint.lstrip("/")}'
        headers = {'Rocket-Pay-Key': self.api_token, 'Content-Type': 'application/json'}

        try:
            async with aiohttp.ClientSession() as session:
                request_kwargs: dict[str, Any] = {'headers': headers}

                if method.upper() in ('GET', 'DELETE'):
                    if data:
                        request_kwargs['params'] = data
                elif data is not None:
                    request_kwargs['json'] = data

                async with session.request(method, url, **request_kwargs) as response:
                    response_data = await response.json()

                    if response.status in (200, 201) and response_data.get('success'):
                        return response_data.get('data')

                    logger.error(
                        'xRocket API ошибка',
                        status=response.status,
                        response_data=response_data,
                    )
                    return None

        except Exception as e:
            logger.error('Ошибка запроса к xRocket API', error=e)
            return None

    async def get_app_info(self) -> dict[str, Any] | None:
        return await self._make_request('GET', 'app/info')

    async def get_version(self) -> dict[str, Any] | None:
        return await self._make_request('GET', 'version')

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
            'amount': round(float(amount), 9),
            'numPayments': 1,
            'currency': currency,
            'commentsEnabled': False,
        }

        if description:
            data['description'] = description[:1000]

        if payload:
            data['payload'] = payload

        if expires_in:
            # xRocket: максимум 1 сутки
            data['expiredIn'] = min(int(expires_in), 86400)

        if callback_url:
            data['callbackUrl'] = callback_url

        result = await self._make_request('POST', 'tg-invoices', data)

        if result:
            logger.info(
                'Создан xRocket invoice',
                invoice_id=result.get('id'),
                amount=amount,
                currency=currency,
            )

        return result

    async def get_invoice(self, invoice_id: str | int) -> dict[str, Any] | None:
        return await self._make_request('GET', f'tg-invoices/{invoice_id}')

    async def delete_invoice(self, invoice_id: str | int) -> bool:
        result = await self._make_request('DELETE', f'tg-invoices/{invoice_id}')
        return result is not None

    async def get_fiat_rate(self, crypto: str, fiat: str = 'RUB') -> float | None:
        """Курс 1 {crypto} = N {fiat}.

        Цепочка источников (Trade API xRocket с июля 2026 отдаёт 404):
        1) публичный Trade API xRocket — на случай, если эндпоинт оживёт;
        2) CryptoBot getExchangeRates — токен уже настроен в боте;
        3) статический резерв из env XROCKET_FALLBACK_USDT_RUB (только USDT/RUB).

        Сбои отдельных источников — warning (без репорта в админку); error —
        только когда недоступны ВСЕ источники (платёж будет отменён).
        """
        rate = await self._get_rate_xrocket_trade(crypto, fiat)
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

    async def _get_rate_xrocket_trade(self, crypto: str, fiat: str) -> float | None:
        """Публичный Trade API xRocket (без авторизации). Content-type-safe."""
        url = f'{self.TRADE_URL}/rates/fiat/{crypto.upper()}/{fiat.upper()}'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    raw = await response.text()
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        logger.warning(
                            'xRocket Trade API: не-JSON ответ (эндпоинт недоступен?)',
                            status=response.status,
                            body=raw[:200],
                        )
                        return None
                    if response.status == 200 and data.get('success'):
                        rate = data.get('data', {}).get('rate')
                        if rate and float(rate) > 0:
                            return float(rate)
                    logger.warning(
                        'xRocket Trade API: курс не получен',
                        status=response.status,
                        crypto=crypto,
                        fiat=fiat,
                    )
                    return None
        except Exception as e:
            logger.warning('xRocket Trade API: ошибка запроса курса', crypto=crypto, fiat=fiat, error=str(e))
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
            for item in rates:
                if (
                    str(item.get('source', '')).upper() == crypto.upper()
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

    async def get_available_currencies(self) -> dict[str, dict] | None:
        """{'USDT': {...minInvoice...}, ...} — публичный эндпоинт Pay API."""
        url = f'{self.base_url}/currencies/available'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    data = await response.json()
                    if response.status == 200 and data.get('success'):
                        results = data.get('data', {}).get('results', [])
                        return {c['currency']: c for c in results if c.get('currency')}
                    return None
        except Exception as e:
            logger.error('Ошибка запроса списка валют xRocket', error=e)
            return None

    async def get_min_invoice(self, currency: str) -> float | None:
        currencies = await self.get_available_currencies()
        if not currencies:
            return None
        info = currencies.get(currency.upper())
        return float(info['minInvoice']) if info and info.get('minInvoice') else None

    def verify_webhook_signature(self, body: str, signature: str) -> bool:
        """HMAC-SHA256(SHA256(api_token), raw_body) — как в официальном SDK."""
        token = self.api_token
        if not token:
            logger.error('xRocket API token не настроен, отклоняем webhook')
            return False

        if not signature:
            return False

        try:
            secret = hashlib.sha256(token.encode()).digest()
            expected = hmac.new(secret, body.encode('utf-8'), hashlib.sha256).hexdigest()

            if hmac.compare_digest(signature.strip().lower(), expected):
                return True

            logger.error(
                'Неверная подпись xRocket webhook',
                received_signature=signature,
                body_length=len(body),
            )
            return False

        except Exception as e:
            logger.error('Ошибка проверки подписи xRocket webhook', error=e)
            return False

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
