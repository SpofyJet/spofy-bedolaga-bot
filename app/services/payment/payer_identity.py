"""Данные плательщика для шлюзов, которые требуют их в каждом платеже.

Platega (docs.platega.io, «Создание платежной ссылки с заданным методом»):
``metadata.userId`` и ``metadata.userName`` — строки, обязательные для части
категорий магазинов. «Отсутствие ``metadata.userId`` при наличии требования
отключает антифрод-защиту и может привести к отключению магазина».

MulenPay (письмо провайдера, 2026-09-15): поле ``client`` «требуется заполнять
почтой, телефоном или ТГ ид и т.п.». Документация формата не задаёт — в примере
только почта.

Platega (обновление docs.platega.io от 2026-10-30): ``metadata.user_email``
обязателен в каждом платеже и должен обозначать покупателя, а не заказ. Почту у
пользователя не спрашиваем — лишний шаг перед оплатой. Подставляем сами:
Telegram ID → ``<id>@telegram.org`` (не меняется при смене username или почты,
так делает и upstream), у аккаунта без Telegram — его почта, если она
корректна, иначе синтетический адрес на нашем домене. В отличие от upstream
платёж из-за почты никогда не отклоняется.

Все поля всегда непустые: у любого плательщика есть хотя бы внутренний id —
Telegram ID, ``user-<id>`` у пользователей без Telegram, ``guest-<хеш токена>`` у
гостей лендинга. Получение данных не имеет права сорвать платёж: любая ошибка
чтения даёт плательщика по одному id.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

import structlog
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger(__name__)

#: Предел выбран защитно (шлюзы длину не документируют) и совпадает с колонками
#: users.email / users.username, чтобы обрезка была недостижима на живых данных.
PAYER_FIELD_MAX_LENGTH = 255
_EMAIL_ADAPTER = TypeAdapter(EmailStr)
#: Домен синтетических адресов, если CABINET_URL не задан.
_FALLBACK_EMAIL_DOMAIN = 'spofyltd.ru'


def _valid_email(value: str | None) -> str | None:
    """Адрес, который пройдёт проверку шлюза, или ``None``. Сам адрес в журнал не пишем."""
    if not value:
        return None
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > PAYER_FIELD_MAX_LENGTH
        or any(c.isspace() or c in '<>' or unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in candidate)
    ):
        return None
    try:
        _EMAIL_ADAPTER.validate_python(candidate)
    except ValueError:
        return None
    return candidate


def _synthetic_email_domain() -> str:
    try:
        from urllib.parse import urlsplit

        from app.config import settings

        host = (urlsplit(settings.CABINET_URL or '').hostname or '').lower()
        if host and '.' in host and host not in {'example.com', 'localhost'}:
            # sub.example.ru / lk.example.ru → example.ru: адрес покупателя, а не поддомена.
            return '.'.join(host.split('.')[-2:])
    except Exception:
        pass
    return _FALLBACK_EMAIL_DOMAIN


def synthetic_payer_email(identifier: str) -> str:
    """Стабильный адрес-идентификатор: тот же плательщик → тот же адрес."""
    local = (
        ''.join(c if c.isascii() and (c.isalnum() or c in '-_.') else '-' for c in identifier).strip('.-') or 'payer'
    )
    return f'{local[:64]}@{_synthetic_email_domain()}'


def platega_email_for(*, telegram_id: str | None, email: str | None, fallback_id: str) -> str:
    """Email-идентификатор плательщика для Platega. Всегда валиден, никогда не пуст."""
    if telegram_id:
        return f'{telegram_id}@telegram.org'
    return _valid_email(email) or synthetic_payer_email(fallback_id)


@dataclass(frozen=True, slots=True)
class PayerIdentity:
    """Кто платит, в трёх видах, которые спрашивают шлюзы."""

    #: Стабильный идентификатор в нашей системе (Platega ``userId``).
    user_id: str
    #: Как человека назвать (Platega ``userName``).
    user_name: str
    #: Как с ним связаться (MulenPay ``client``).
    contact: str
    #: Только идентификация в Platega (``metadata.user_email``), не для чеков.
    platega_email: str | None = None

    def platega_metadata(self) -> dict[str, str]:
        email = _valid_email(self.platega_email) or synthetic_payer_email(self.user_id)
        return {'userId': self.user_id, 'userName': self.user_name, 'user_email': email}


@dataclass(frozen=True, slots=True)
class PayerRecord:
    """Поля пользователя, из которых собирается плательщик."""

    id: int
    telegram_id: int | None
    username: str | None
    first_name: str | None
    last_name: str | None
    email: str | None
    email_verified: bool


def _clean(value: object) -> str | None:
    """Строка без обрезанных эмодзи и управляющих символов; пустая — ``None``.

    Имена из Telegram бывают с одиноким суррогатом (обрезанный эмодзи): в JSON он
    уходит экранированной половинкой символа, и строгий разборщик шлюза отбивает
    весь платёж.
    """
    if value is None:
        return None
    text = ''.join(
        char
        for char in str(value)
        if not 0xD800 <= ord(char) <= 0xDFFF and unicodedata.category(char) not in ('Cc', 'Cf')
    )
    text = ' '.join(text.split())
    return text[:PAYER_FIELD_MAX_LENGTH] or None


def _first(*candidates: str | None) -> str:
    return next(candidate for candidate in candidates if candidate)


def _by_id(identifier: str) -> PayerIdentity:
    return PayerIdentity(user_id=identifier, user_name=identifier, contact=identifier)


def payer_from_user(record: PayerRecord) -> PayerIdentity:
    """Плательщик-пользователь.

    ``userName``: @username → имя → почта → id<telegram_id>. Контакт: только
    подтверждённая почта (адрес назначается до подтверждения, а MulenPay
    фискализирует платёж — чек чужому ящику не нужен), иначе Telegram ID.
    """
    telegram_id = str(record.telegram_id) if record.telegram_id else None
    user_id = telegram_id or f'user-{record.id}'
    username = _clean((record.username or '').lstrip('@'))
    full_name = _clean(' '.join(part for part in (record.first_name, record.last_name) if part))
    email = _clean(record.email)
    return PayerIdentity(
        user_id=user_id,
        user_name=_first(
            f'@{username}'[:PAYER_FIELD_MAX_LENGTH] if username else None,
            full_name,
            email,
            f'id{telegram_id}' if telegram_id else None,
            user_id,
        ),
        contact=_first(email if record.email_verified else None, telegram_id, user_id),
        platega_email=platega_email_for(telegram_id=telegram_id, email=record.email, fallback_id=user_id),
    )


def guest_payer_id(purchase_token: str) -> str:
    """Идентификатор гостя: сам токен покупки наружу не отдаём — по нему забирают подписку."""
    return 'guest-' + hashlib.sha256(purchase_token.encode()).hexdigest()[:16]


def payer_from_guest(purchase_token: str, *, contact_type: str | None, contact_value: str | None) -> PayerIdentity:
    """Гость лендинга: аккаунта нет, есть контакт, который он оставил (почта или Telegram)."""
    user_id = guest_payer_id(purchase_token)
    contact = _clean(contact_value) if contact_type in ('email', 'telegram') else None
    # Гостевой @username не постоянный идентификатор — для Platega только почта гостя,
    # иначе синтетический адрес по id гостя.
    return PayerIdentity(
        user_id=user_id,
        user_name=_first(contact, user_id),
        contact=_first(contact, user_id),
        platega_email=platega_email_for(
            telegram_id=None, email=contact_value if contact_type == 'email' else None, fallback_id=user_id
        ),
    )


async def resolve_user_payer(db: AsyncSession, user_id: int) -> PayerIdentity:
    """Плательщик по id пользователя. Точечный select — это горячий путь оплаты."""
    from app.database.models import User

    try:
        result = await db.execute(
            select(
                User.id,
                User.telegram_id,
                User.username,
                User.first_name,
                User.last_name,
                User.email,
                User.email_verified,
            ).where(User.id == user_id)
        )
        row = result.first()
    except Exception as error:
        logger.warning('Не удалось прочитать плательщика — отправляем только id', user_id=user_id, error=str(error))
        row = None
    if row is None:
        return _by_id(f'user-{user_id}')
    return payer_from_user(
        PayerRecord(
            id=row.id,
            telegram_id=row.telegram_id,
            username=row.username,
            first_name=row.first_name,
            last_name=row.last_name,
            email=row.email,
            email_verified=bool(row.email_verified),
        )
    )


async def resolve_guest_payer(db: AsyncSession, purchase_token: str) -> PayerIdentity:
    """Плательщик-гость по токену покупки лендинга."""
    try:
        from app.database.crud.landing import get_purchase_by_token

        purchase = await get_purchase_by_token(db, purchase_token)
    except Exception as error:
        logger.warning('Не удалось прочитать гостевую покупку — отправляем только id', error=str(error))
        purchase = None
    return payer_from_guest(
        purchase_token,
        contact_type=getattr(purchase, 'contact_type', None),
        contact_value=getattr(purchase, 'contact_value', None),
    )
