import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.faq import (
    get_faq_page_by_id,
    get_faq_pages,
    get_faq_setting,
)
from app.database.models import FaqPage


logger = structlog.get_logger(__name__)


class FaqService:
    MAX_PAGE_LENGTH = 3500

    @staticmethod
    def _normalize_language(language: str) -> str:
        base_language = language or settings.DEFAULT_LANGUAGE or 'ru'
        return base_language.split('-')[0].lower()

    @staticmethod
    def normalize_language(language: str) -> str:
        return FaqService._normalize_language(language)

    @classmethod
    async def is_enabled(cls, db: AsyncSession, language: str) -> bool:
        pages = await cls.get_pages(db, language)
        return bool(pages)

    @classmethod
    async def get_pages(
        cls,
        db: AsyncSession,
        language: str,
        *,
        include_inactive: bool = False,
        fallback: bool = True,
    ) -> list[FaqPage]:
        lang = cls._normalize_language(language)
        pages = await get_faq_pages(db, lang, include_inactive=include_inactive)

        if pages:
            setting = await get_faq_setting(db, lang)
            if setting and not setting.is_enabled and not include_inactive:
                return []
            return pages

        if not fallback:
            return []

        default_lang = cls._normalize_language(settings.DEFAULT_LANGUAGE)
        if lang == default_lang:
            return []

        fallback_pages = await get_faq_pages(
            db,
            default_lang,
            include_inactive=include_inactive,
        )

        if not fallback_pages:
            return []

        setting = await get_faq_setting(db, default_lang)
        if setting and not setting.is_enabled and not include_inactive:
            return []

        return fallback_pages

    @classmethod
    async def get_page(
        cls,
        db: AsyncSession,
        page_id: int,
        language: str,
        *,
        fallback: bool = True,
        include_inactive: bool = False,
    ) -> FaqPage | None:
        page = await get_faq_page_by_id(db, page_id)
        if not page:
            return None

        lang = cls._normalize_language(language)
        default_lang = cls._normalize_language(settings.DEFAULT_LANGUAGE)

        if not include_inactive and not page.is_active:
            return None

        if page.language == lang:
            return page

        if fallback and page.language == default_lang:
            return page

        return None
