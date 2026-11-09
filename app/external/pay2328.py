"""HTTP client for the 2328.io payment API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import aiohttp
import structlog

from app.config import settings


logger = structlog.get_logger(__name__)

USER_AGENT = 'SpofyBot/1.0'


class Pay2328Service:
    """Wrapper around the payment endpoints of the 2328.io API."""

    def __init__(self) -> None:
        self.base_url = settings.PAY2328_BASE_URL.rstrip('/')
        self.merchant_id = settings.PAY2328_MERCHANT_ID
        self.api_key = settings.PAY2328_API_KEY

    @property
    def is_configured(self) -> bool:
        return bool(self.merchant_id and self.api_key)

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))

    def _sign(self, body: str) -> str:
        encoded = base64.b64encode(body.encode('utf-8'))
        return hmac.new((self.api_key or '').encode('utf-8'), encoded, hashlib.sha256).hexdigest()

    async def _request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.is_configured:
            logger.error('2328.io не настроен: нет merchant id или api key')
            return None

        body = self._serialize({key: value for key, value in payload.items() if value is not None})
        headers = {
            'project': self.merchant_id or '',
            'sign': self._sign(body),
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
        }
        url = f'{self.base_url}/{endpoint.lstrip("/")}'

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(url, data=body.encode('utf-8'), headers=headers) as response,
            ):
                text = await response.text()
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    logger.error('Ответ 2328.io не JSON', endpoint=endpoint, response_status=response.status)
                    return None

                if response.status >= 400:
                    logger.error('2328.io вернул ошибку', endpoint=endpoint, response_status=response.status, data=data)
                    return None

                if isinstance(data, dict) and data.get('state') == 0:
                    return data

                logger.error('2328.io вернул неуспешный ответ', endpoint=endpoint, data=data)
                return None
        except (aiohttp.ClientError, TimeoutError) as error:
            logger.error('Ошибка запроса к 2328.io', endpoint=endpoint, error=error)
            return None

    async def create_payment(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return await self._request('payment', payload)

    async def get_payment_info(
        self,
        *,
        uuid: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not uuid and not order_id:
            raise ValueError('Нужно указать uuid или order_id для 2328.io payment/info')

        return await self._request('payment/info', {'uuid': uuid, 'order_id': order_id})

    def verify_webhook_signature(self, payload: dict[str, Any]) -> bool:
        if not self.is_configured:
            logger.error('2328.io не настроен, отклоняем webhook')
            return False

        if not isinstance(payload, dict):
            logger.error('Webhook 2328.io не объект')
            return False

        signature = payload.get('sign')
        if not signature:
            logger.error('Webhook 2328.io без подписи')
            return False

        unsigned = {key: value for key, value in payload.items() if key != 'sign'}
        is_valid = hmac.compare_digest(self._sign(self._serialize(unsigned)), str(signature))
        if not is_valid:
            logger.error('Неверная подпись webhook 2328.io')
        return is_valid
