import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.public_offer import (
    get_public_offer,
)
from app.database.models import PublicOffer


logger = structlog.get_logger(__name__)


class PublicOfferService:
    """Helpers for managing the public offer text and visibility."""

    MAX_PAGE_LENGTH = 3500

    @staticmethod
    def _normalize_language(language: str) -> str:
        base_language = language or settings.DEFAULT_LANGUAGE or 'ru'
        return base_language.split('-')[0].lower()

    @staticmethod
    def normalize_language(language: str) -> str:
        return PublicOfferService._normalize_language(language)

    @classmethod
    async def get_offer(
        cls,
        db: AsyncSession,
        language: str,
        *,
        fallback: bool = False,
    ) -> PublicOffer | None:
        lang = cls._normalize_language(language)
        offer = await get_public_offer(db, lang)

        if offer or not fallback:
            return offer

        default_lang = cls._normalize_language(settings.DEFAULT_LANGUAGE)
        if lang != default_lang:
            return await get_public_offer(db, default_lang)

        return offer

    @classmethod
    async def get_active_offer(
        cls,
        db: AsyncSession,
        language: str,
    ) -> PublicOffer | None:
        lang = cls._normalize_language(language)
        offer = await get_public_offer(db, lang)

        if offer:
            if offer.is_enabled and offer.content.strip():
                return offer

            if not offer.is_enabled:
                return None

        default_lang = cls._normalize_language(settings.DEFAULT_LANGUAGE)
        if lang != default_lang:
            fallback_offer = await get_public_offer(db, default_lang)
            if fallback_offer and fallback_offer.is_enabled and fallback_offer.content.strip():
                return fallback_offer

        return None

    @classmethod
    async def is_offer_enabled(cls, db: AsyncSession, language: str) -> bool:
        offer = await cls.get_active_offer(db, language)
        return offer is not None
