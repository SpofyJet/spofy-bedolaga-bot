"""Server/country management endpoints.

GET /subscription/countries
POST /subscription/countries
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter


logger = structlog.get_logger(__name__)

router = APIRouter()
