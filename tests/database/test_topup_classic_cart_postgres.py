"""Real provider finalizers → wallet hook → cart → purchase on PostgreSQL.

Only key/value storage, notifications and panel transport are fake. Payment
credit, common dispatch, pricing, purchase persistence and ledgers are real.
"""

import fnmatch
import os
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.services.user_cart_service import UserCartService
from tests.fixtures.real_redis import ensure_real_redis
from tests.fixtures.redis_pipeline import SequentialPipelineMixin


pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]


class CartStorage(SequentialPipelineMixin):
    def __init__(self):
        self.values = {}

    async def setex(self, key, ttl, value):
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def exists(self, key):
        return int(key in self.values)

    async def delete(self, *keys):
        return sum(self.values.pop(key, None) is not None for key in keys)

    async def scan(self, cursor=0, match='*', count=50):
        return 0, [key for key in self.values if fnmatch.fnmatch(key, match)]


@pytest_asyncio.fixture
async def cart_service(monkeypatch):
    service = UserCartService()
    url = os.environ.get('TEST_CART_REDIS_URL')
    service._redis_client = ensure_real_redis(monkeypatch).create_redis(url) if url else CartStorage()
    service._initialized = True
    if not url:
        # Sequential storage boundary for the standalone PostgreSQL profile;
        # the combined Redis/PostgreSQL profile executes the real Lua script.
        async def cleanup(user_id, processed):
            await service.delete_subscription_cart(user_id, processed['subscription_id'])
            return await service.delete_user_cart(user_id)

        service.delete_processed_cart = AsyncMock(side_effect=cleanup)
    try:
        yield service
    finally:
        if url:
            await service._redis_client.delete(
                'user_cart:1',
                'user_cart:1:sub:10',
                'user_cart:1:sub:20',
                'cart_topup_intent:1',
                'cart_topup_intent:1:sub:10',
                'cart_topup_intent:1:sub:20',
            )
            await service._redis_client.aclose()
