import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.privacy_policy import (
    get_privacy_policy,
)
from app.database.models import PrivacyPolicy


logger = structlog.get_logger(__name__)


class PrivacyPolicyService:
    """Utility helpers around privacy policy storage and presentation."""

    MAX_PAGE_LENGTH = 3500

    @staticmethod
    def _normalize_language(language: str) -> str:
        base_language = language or settings.DEFAULT_LANGUAGE or 'ru'
        return base_language.split('-')[0].lower()

    @staticmethod
    def normalize_language(language: str) -> str:
        return PrivacyPolicyService._normalize_language(language)

    @classmethod
    async def get_policy(
        cls,
        db: AsyncSession,
        language: str,
        *,
        fallback: bool = False,
    ) -> PrivacyPolicy | None:
        lang = cls._normalize_language(language)
        policy = await get_privacy_policy(db, lang)

        if policy or not fallback:
            return policy

        default_lang = cls._normalize_language(settings.DEFAULT_LANGUAGE)
        if lang != default_lang:
            return await get_privacy_policy(db, default_lang)

        return policy

    @classmethod
    async def get_active_policy(
        cls,
        db: AsyncSession,
        language: str,
    ) -> PrivacyPolicy | None:
        lang = cls._normalize_language(language)
        policy = await get_privacy_policy(db, lang)

        if policy and policy.is_enabled and policy.content.strip():
            return policy

        default_lang = cls._normalize_language(settings.DEFAULT_LANGUAGE)
        if lang != default_lang:
            fallback_policy = await get_privacy_policy(db, default_lang)
            if fallback_policy and fallback_policy.is_enabled and fallback_policy.content.strip():
                return fallback_policy

        return None

    @classmethod
    async def is_policy_enabled(cls, db: AsyncSession, language: str) -> bool:
        policy = await cls.get_active_policy(db, language)
        return policy is not None
