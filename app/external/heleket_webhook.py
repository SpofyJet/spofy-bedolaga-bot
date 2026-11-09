import json
from typing import Any

import structlog
from aiohttp import web

from app.config import settings
from app.database.database import AsyncSessionLocal
from app.external.heleket import HeleketService
from app.services.payment_service import PaymentService


logger = structlog.get_logger(__name__)


class HeleketWebhookHandler:
    def __init__(self, payment_service: PaymentService) -> None:
        self.payment_service = payment_service
        self.service = HeleketService()

    async def handle(self, request: web.Request) -> web.Response:
        if not settings.is_heleket_enabled():
            logger.warning('Получен Heleket webhook, но сервис отключен')
            return web.json_response({'status': 'error', 'reason': 'disabled'}, status=503)

        try:
            payload: dict[str, Any] = await request.json()
        except json.JSONDecodeError:
            logger.error('Некорректный JSON Heleket webhook')
            return web.json_response({'status': 'error', 'reason': 'invalid_json'}, status=400)

        if not self.service.verify_webhook_signature(payload):
            return web.json_response({'status': 'error', 'reason': 'invalid_signature'}, status=401)

        processed: bool | None = None
        async with AsyncSessionLocal() as db:
            try:
                processed = await self.payment_service.process_heleket_webhook(db, payload)
                await db.commit()
            except Exception as e:
                logger.error('Ошибка обработки Heleket webhook', error=e)
                await db.rollback()
                return web.json_response({'status': 'error', 'reason': 'internal_error'}, status=500)

        if processed:
            return web.json_response({'status': 'ok'}, status=200)

        return web.json_response({'status': 'error', 'reason': 'not_processed'}, status=400)

    async def health_check(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                'status': 'ok',
                'service': 'heleket_webhook',
                'enabled': settings.is_heleket_enabled(),
                'path': settings.HELEKET_WEBHOOK_PATH,
            }
        )

    async def options_handler(self, _: web.Request) -> web.Response:
        return web.Response(
            status=200,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            },
        )
