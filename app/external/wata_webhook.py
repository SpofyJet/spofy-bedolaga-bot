from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime, timedelta

import structlog
from aiohttp import ClientSession, ClientTimeout, ContentTypeError, web
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.config import settings
from app.services.payment_service import PaymentService


logger = structlog.get_logger(__name__)


class WataPublicKeyProvider:
    """Loads and caches the WATA public key used for webhook signature validation."""

    def __init__(self, *, cache_seconds: int | None = None) -> None:
        self._cache_seconds = cache_seconds or int(settings.WATA_PUBLIC_KEY_CACHE_SECONDS)
        self._cached_key: str | None = None
        self._expires_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def get_public_key(self) -> str | None:
        """Returns a cached public key or fetches a new one from WATA."""

        now = datetime.now(UTC)
        if self._cached_key and self._expires_at and now < self._expires_at:
            return self._cached_key

        async with self._lock:
            now = datetime.now(UTC)
            if self._cached_key and self._expires_at and now < self._expires_at:
                return self._cached_key

            key = await self._fetch_public_key()
            if key:
                self._cached_key = key
                if self._cache_seconds > 0:
                    self._expires_at = datetime.now(UTC) + timedelta(seconds=self._cache_seconds)
                else:
                    self._expires_at = None
                logger.debug('Получен и закеширован публичный ключ WATA')
                return self._cached_key

            if self._cached_key:
                logger.warning('Используем ранее закешированный публичный ключ WATA')
                return self._cached_key

            logger.error('Публичный ключ WATA недоступен')
            return None

    async def _fetch_public_key(self) -> str | None:
        url = settings.WATA_PUBLIC_KEY_URL or f'{settings.WATA_BASE_URL.rstrip("/")}/public-key'
        timeout = ClientTimeout(total=settings.WATA_REQUEST_TIMEOUT)

        try:
            async with ClientSession(timeout=timeout) as session, session.get(url) as response:
                text = await response.text()
                if response.status >= 400:
                    logger.error('Ошибка получения публичного ключа WATA', response_status=response.status, text=text)
                    return None

                try:
                    payload = await response.json()
                except ContentTypeError:
                    logger.error('Ответ WATA public-key не является JSON', text=text)
                    return None

            if isinstance(payload, dict):
                value = payload.get('value')
                if value:
                    return value
                logger.error('Ответ WATA public-key не содержит ключ', payload=payload)
            else:
                logger.error('Неожиданный формат ответа WATA public-key', payload=payload)
        except Exception as error:
            logger.error('Ошибка запроса публичного ключа WATA', error=error)

        return None


class WataWebhookHandler:
    """Processes webhook callbacks coming from WATA."""

    def __init__(
        self,
        payment_service: PaymentService,
        *,
        public_key_provider: WataPublicKeyProvider | None = None,
    ) -> None:
        self.payment_service = payment_service
        self.public_key_provider = public_key_provider or WataPublicKeyProvider()

    async def _verify_signature(self, raw_body: str, signature: str) -> bool:
        signature = (signature or '').strip()
        if not signature:
            logger.error('WATA webhook без подписи')
            return False

        public_key_pem = await self.public_key_provider.get_public_key()
        if not public_key_pem:
            logger.error('Публичный ключ WATA отсутствует, проверка подписи невозможна')
            return False

        try:
            signature_bytes = base64.b64decode(signature)
        except (ValueError, TypeError):
            logger.error('Некорректная подпись WATA (не Base64)')
            return False

        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
        except ValueError as error:
            logger.error('Ошибка загрузки публичного ключа WATA', error=error)
            return False

        try:
            public_key.verify(
                signature_bytes,
                raw_body.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA512(),
            )
            return True
        except InvalidSignature:
            logger.warning('Подпись WATA webhook не прошла проверку')
            return False
        except Exception as error:
            logger.error('Ошибка проверки подписи WATA', error=error)
            return False

    async def health_check(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                'status': 'ok',
                'service': 'wata_webhook',
                'enabled': settings.is_wata_enabled(),
                'path': settings.WATA_WEBHOOK_PATH,
            }
        )

    async def options_handler(self, _: web.Request) -> web.Response:
        return web.Response(
            status=200,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-Signature',
            },
        )
