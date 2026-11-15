"""The cabinet's saved device checkout must retain the selected subscription."""

import pytest

from tests.services.test_cart_cleanup_redis import (
    carts,  # noqa: F401 - shared real Redis fixture
)


pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]
