import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.faq import (
    get_faq_page_by_id,
    get_faq_pages,
    get_faq_setting,
    set_faq_enabled,
)
from app.database.models import FaqPage, FaqSetting


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
    async def set_enabled(
        cls,
        db: AsyncSession,
        language: str,
        enabled: bool,
    ) -> FaqSetting:
        lang = cls._normalize_language(language)
        return await set_faq_enabled(db, lang, enabled)

    @classmethod
    async def toggle_enabled(
        cls,
        db: AsyncSession,
        language: str,
    ) -> FaqSetting:
        lang = cls._normalize_language(language)
        setting = await get_faq_setting(db, lang)
        new_status = True
        if setting:
            new_status = not setting.is_enabled
        return await set_faq_enabled(db, lang, new_status)

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

    @staticmethod
    def split_content_into_pages(
        content: str,
        *,
        max_length: int | None = None,
    ) -> list[str]:
        if not content:
            return []

        normalized = content.replace('\r\n', '\n').strip()
        if not normalized:
            return []

        limit = max_length or FaqService.MAX_PAGE_LENGTH
        if len(normalized) <= limit:
            return [normalized]

        paragraphs = [paragraph.strip() for paragraph in normalized.split('\n\n') if paragraph.strip()]

        pages: list[str] = []
        current = ''

        def flush_current() -> None:
            nonlocal current
            if current:
                pages.append(current.strip())
                current = ''

        for paragraph in paragraphs:
            candidate = f'{current}\n\n{paragraph}'.strip() if current else paragraph
            if len(candidate) <= limit:
                current = candidate
                continue

            flush_current()

            if len(paragraph) <= limit:
                current = paragraph
                continue

            start = 0
            while start < len(paragraph):
                chunk = paragraph[start : start + limit]
                pages.append(chunk.strip())
                start += limit

            current = ''

        flush_current()

        if not pages:
            return [normalized[:limit]]

        return pages
