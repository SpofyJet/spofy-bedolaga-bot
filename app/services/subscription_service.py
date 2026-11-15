import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud.user import get_user_by_id
from app.database.models import Subscription, SubscriptionStatus, User
from app.external.remnawave_api import (
    RemnaWaveAPI,
    RemnaWaveAPIError,
    RemnaWaveUser,
    is_user_not_found_error,
)
from app.external.remnawave_errors import coerce_panel_user_id

# Правила поля стратегии живут в пакете синхронизации; имя оставлено здесь для
# внешнего кода, который импортировал его из сервиса.
from app.services.panel_sync import (
    PanelIdentity,
    build_panel_payload,
    get_traffic_reset_strategy as get_traffic_reset_strategy,  # noqa: PLC0414
    is_subscription_live,
    link_subscription_panel_identity,
    panel_date_is_closing,
    panel_id_is_free_for,
    push_subscription,
    resolve_panel_user_tag,
)
from app.services.panel_sync.writer import DeviceLimitReconciliationError
from app.utils.subscription_utils import (
    resolve_hwid_device_limit_for_payload,
)


logger = structlog.get_logger(__name__)


async def reload_after_panel_failure(db: AsyncSession, *objects: Any) -> None:
    """Перечитать объекты, которые откат сессии пометил протухшими.

    create_remnawave_user и update_remnawave_user при сбое панели делают db.rollback() и
    возвращают None. Откат помечает протухшими ВСЕ объекты сессии, и первое же чтение поля
    (tariff.name, user.id) в async-коде падает с MissingGreenlet. Оплата к этому моменту уже
    закоммичена, поэтому человек после списания видел «Не получилось продлить подписку.
    Попробуйте ещё раз» (сбой панели 02.11.2026: 9 из 12 плативших, один оплатил дважды).

    Вызывать после обращения к панели и только там, где деньги и подписка уже закоммичены:
    несохранённые правки откат стёр, перечитанный объект покажет то, что лежит в базе.
    Панель ответила — объекты не протухли, запросов в базу нет.
    """
    for obj in objects:
        state = sa_inspect(obj, raiseerr=False) if obj is not None else None
        if state is None or not getattr(state, 'persistent', False) or not state.expired:
            continue
        try:
            await db.refresh(obj)
        except Exception as error:
            logger.warning('Не удалось перечитать объект после сбоя панели', kind=type(obj).__name__, error=error)


@dataclass(frozen=True)
class SubscriptionReissueResult:
    subscription_url: str
    devices_reset: bool


class SubscriptionService:
    def __init__(self):
        self._config_error: str | None = None
        self.api: RemnaWaveAPI | None = None
        self._last_config_signature: tuple[str, ...] | None = None
        # Панель не ответила на запрос этого сервиса. Экран «Моя подписка» после первого сбоя
        # к панели больше не ходит: каждый следующий запрос — ещё до двух минут ожидания.
        self.panel_failed = False

        self._refresh_configuration()

    def _refresh_configuration(self) -> None:
        auth_params = settings.get_remnawave_auth_params()
        base_url = (auth_params.get('base_url') or '').strip()
        api_key = (auth_params.get('api_key') or '').strip()
        secret_key = (auth_params.get('secret_key') or '').strip() or None
        username = (auth_params.get('username') or '').strip() or None
        password = (auth_params.get('password') or '').strip() or None
        caddy_token = (auth_params.get('caddy_token') or '').strip() or None
        auth_type = (auth_params.get('auth_type') or 'api_key').strip()

        config_signature = (
            base_url,
            api_key,
            secret_key or '',
            username or '',
            password or '',
            caddy_token or '',
            auth_type,
        )

        if config_signature == self._last_config_signature:
            return

        if not base_url:
            self._config_error = 'REMNAWAVE_API_URL не настроен'
            self.api = None
        elif not api_key:
            self._config_error = 'REMNAWAVE_API_KEY не настроен'
            self.api = None
        else:
            self._config_error = None
            self.api = RemnaWaveAPI(
                base_url=base_url,
                api_key=api_key,
                secret_key=secret_key,
                username=username,
                password=password,
                caddy_token=caddy_token,
                auth_type=auth_type,
            )

        if self._config_error:
            logger.warning(
                'RemnaWave API недоступен. Подписочный сервис будет работать в оффлайн-режиме.',
                config_error=self._config_error,
            )

        self._last_config_signature = config_signature

    @staticmethod
    def _resolve_user_tag(subscription: Subscription) -> str | None:
        # Тег тарифа побеждает, иначе общие TRIAL/PAID из настроек (panel_sync.tags).
        return resolve_panel_user_tag(subscription)

    @property
    def is_configured(self) -> bool:
        return self._config_error is None

    @property
    def configuration_error(self) -> str | None:
        return self._config_error

    def _ensure_configured(self) -> None:
        self._refresh_configuration()
        if not self.api or not self.is_configured:
            raise RemnaWaveAPIError(self._config_error or 'RemnaWave API не настроен')

    @asynccontextmanager
    async def get_api_client(self):
        self._ensure_configured()
        assert self.api is not None
        async with self.api as api:
            yield api

    async def sync_remnawave_user(
        self,
        db: AsyncSession,
        subscription: Subscription,
        *,
        reset_traffic: bool = False,
        reset_reason: str | None = None,
    ) -> RemnaWaveUser | None:
        """Создать пользователя панели или обновить — по тому, известен ли панели его id.

        Id панели живёт у пользователя (аккаунт в панели один на человека).
        Нет id — create_remnawave_user (это upsert: пользователя,
        которого панель уже знает, он обновит); есть — update_remnawave_user. Свежая подписка
        (награда за реферала, купон, покупка) id ещё не имеет, и update для неё падал с
        «RemnaWave id не найден»: человек оставался без пользователя в панели и без ссылки.
        """
        user = await get_user_by_id(db, subscription.user_id)
        panel_id = getattr(user, 'remnawave_id', None)
        if panel_id:
            return await self.update_remnawave_user(
                db, subscription, reset_traffic=reset_traffic, reset_reason=reset_reason
            )
        return await self.create_remnawave_user(
            db, subscription, reset_traffic=reset_traffic, reset_reason=reset_reason
        )

    async def _defer_device_limit_reconciliation(
        self,
        db,
        subscription,
        user,
        *,
        action: Literal['create', 'update'],
        reset_traffic: bool,
        reset_reason: str | None,
    ) -> None:
        # Capture identity before rollback expires SQLAlchemy objects. The paid
        # purchase is already committed; retries only reconcile panel state.
        subscription_id, user_id = subscription.id, subscription.user_id
        from app.services.remnawave_retry_queue import remnawave_retry_queue

        if not remnawave_retry_queue.is_processing(subscription_id):
            remnawave_retry_queue.enqueue(
                subscription_id=subscription_id,
                user_id=user_id,
                action=action,
                reset_traffic=reset_traffic,
                reset_reason=reset_reason,
            )
        await db.rollback()
        await db.refresh(subscription)
        if user is not None:
            await db.refresh(user)

    async def create_remnawave_user(
        self,
        db: AsyncSession,
        subscription: Subscription,
        *,
        reset_traffic: bool = False,
        reset_reason: str | None = None,
    ) -> RemnaWaveUser | None:
        try:
            user = await get_user_by_id(db, subscription.user_id)
            if not user:
                logger.error('Пользователь не найден', user_id=subscription.user_id)
                return None

            validation_success = await self.validate_and_clean_subscription(db, subscription, user)
            if not validation_success:
                logger.error('Ошибка валидации подписки для пользователя', _format_user_log=self._format_user_log(user))
                await db.rollback()
                return None

            await db.flush((subscription, user))
            await db.refresh(subscription)
            await db.refresh(user)

            # Загружаем tariff заранее, чтобы избежать lazy loading в async контексте
            try:
                await db.refresh(subscription, ['tariff'])
            except Exception:
                logger.warning('Ignored error in create_remnawave_user', exc_info=True)
                # tariff может быть None или уже загружен

            user_tag = self._resolve_user_tag(subscription)

            # Определяем внешний сквад из тарифа
            ext_squad_uuid = subscription.tariff.external_squad_uuid if subscription.tariff else None

            async with self.get_api_client() as api:
                hwid_limit = resolve_hwid_device_limit_for_payload(subscription)

                updated_user = await self._create_or_update_remnawave_user_single(
                    api,
                    user,
                    subscription,
                    db=db,
                    user_tag=user_tag,
                    hwid_limit=hwid_limit,
                    ext_squad_uuid=ext_squad_uuid,
                    reset_traffic=reset_traffic,
                    reset_reason=reset_reason,
                )

                subscription.remnawave_short_uuid = updated_user.short_uuid
                subscription.subscription_url = updated_user.subscription_url
                subscription.subscription_crypto_link = updated_user.happ_crypto_link
                if await self._panel_id_is_free_for(db, subscription, updated_user.id):
                    subscription.remnawave_id = updated_user.id
                else:
                    # `uq_subscriptions_remnawave_id` частично-уникален. В
                    # single-tariff соседняя подписка того же человека уже держит
                    # этот аккаунт — ровно то состояние, которое оставляет бэкфилл.
                    # Записать id второй строке значит словить IntegrityError уже
                    # ПОСЛЕ успешного PATCH в панель и откатить оплату вместе с ним.
                    # Адресация не теряется: остаётся `users.remnawave_id`.
                    logger.warning(
                        '⚠️ Панельный id уже закреплён за другой подпиской — адресуем через пользователя',
                        subscription_id=subscription.id,
                        remnawave_id=updated_user.id,
                    )
                # Панель адресуется через человека — держим актуальным.
                user.remnawave_id = updated_user.id

                await db.commit()

                logger.info('✅ Создан/обновлен RemnaWave пользователь для подписки', subscription_id=subscription.id)
                strategy_name = settings.DEFAULT_TRAFFIC_RESET_STRATEGY
                logger.info('📊 Стратегия сброса трафика', strategy_name=strategy_name)
                return updated_user

        except asyncio.CancelledError:
            await db.rollback()
            raise
        except RemnaWaveAPIError as e:
            if isinstance(e, DeviceLimitReconciliationError):
                await self._defer_device_limit_reconciliation(
                    db, subscription, user, action='create', reset_traffic=reset_traffic, reset_reason=reset_reason
                )
                logger.error('HWID limit reconciliation deferred', error=e)
                return None
            await db.rollback()
            logger.error('Ошибка RemnaWave API', error=e)
            return None
        except Exception as e:
            await db.rollback()
            logger.error('Ошибка создания RemnaWave пользователя', error=e)
            return None

    async def _panel_id_is_free_for(self, db: AsyncSession, subscription, panel_id: int | None) -> bool:
        return await panel_id_is_free_for(db, subscription, panel_id)

    async def _adopt_panel_id_for_update(self, db: AsyncSession, subscription, user) -> int | None:
        """Достать числовой id панели по shortUuid и сохранить его на строке.

        Нужно ровно для окна между миграцией 0104 и прогоном бэкфила, когда
        `remnawave_id` пуст у всех доапгрейдных строк. Возвращает None, если
        опознать нечем или панель этот shortUuid не знает — тогда вызывающий
        честно откажется от обновления.
        """
        short_uuid = (getattr(subscription, 'remnawave_short_uuid', None) or '').strip()
        if not short_uuid:
            return None
        try:
            async with self.get_api_client() as api:
                adopted = await api.get_user_by_short_uuid(short_uuid)
        except Exception as error:
            # Транзиент/деградация панели — не повод считать, что аккаунта нет.
            logger.warning(
                '⚠️ Не удалось опознать панельного пользователя по short_uuid для обновления',
                subscription_id=getattr(subscription, 'id', None),
                error=error,
            )
            return None
        if adopted is None:
            return None

        logger.info(
            '🔗 Панельный id восстановлен по short_uuid при обновлении',
            subscription_id=getattr(subscription, 'id', None),
            remnawave_id=adopted.id,
        )
        # Только на User: все подписки одного пользователя указывают на ОДИН
        # панельный аккаунт, а `uq_subscriptions_remnawave_id` частично-уникален —
        # записав id второй строке, мы бы словили IntegrityError и откатили
        # вместе с ним уже применённое пополнение.
        user.remnawave_id = adopted.id
        await db.flush((subscription, user))
        return adopted.id

    async def _push_subscription_to_panel(
        self,
        api: RemnaWaveAPI,
        user: User,
        subscription: Subscription,
        *,
        db: AsyncSession | None = None,
        user_tag: str | None,
        hwid_limit: int | None,
        ext_squad_uuid: str | None,
        reset_traffic: bool,
        reset_reason: str | None,
    ) -> RemnaWaveUser:
        """Отправить подписку в панель через общий сервис синхронизации.

        Поиск аккаунта, сборка полей, создание/обновление и запись связи живут в
        ``app/services/panel_sync``: раньше это были две почти одинаковые копии
        здесь и ещё одиннадцать в других модулях.

        ``hwid_limit`` и ``ext_squad_uuid`` вызывающий считает заранее (он уже
        подгрузил тариф), поэтому здесь они перекрывают то, что сервис вывел бы
        сам, — вычисление одно и то же, но лишний обход тарифа не нужен.
        """
        payload = replace(
            build_panel_payload(user, subscription, user_tag=user_tag),
            hwid_device_limit=hwid_limit,
            external_squad_uuid=ext_squad_uuid,
        )
        result = await push_subscription(
            api,
            user,
            subscription,
            db=db,
            payload=payload,
        )
        if reset_traffic:
            await self._reset_user_traffic(api, result.panel_user.id, user, reset_reason)
        return result.panel_user

    async def _create_or_update_remnawave_user_single(
        self,
        api: RemnaWaveAPI,
        user: User,
        subscription: Subscription,
        *,
        db: AsyncSession | None = None,
        user_tag: str | None,
        hwid_limit: int | None,
        ext_squad_uuid: str | None,
        reset_traffic: bool,
        reset_reason: str | None,
    ) -> RemnaWaveUser:
        """Одиночный режим тарифов: один пользователь панели на человека."""
        return await self._push_subscription_to_panel(
            api,
            user,
            subscription,
            db=db,
            user_tag=user_tag,
            hwid_limit=hwid_limit,
            ext_squad_uuid=ext_squad_uuid,
            reset_traffic=reset_traffic,
            reset_reason=reset_reason,
        )

    async def update_remnawave_user(
        self,
        db: AsyncSession,
        subscription: Subscription,
        *,
        reset_traffic: bool = False,
        reset_reason: str | None = None,
        sync_squads: bool = True,
    ) -> RemnaWaveUser | None:
        try:
            user = await get_user_by_id(db, subscription.user_id)
            if not user:
                logger.error('Пользователь не найден', user_id=subscription.user_id)
                return None

            remnawave_id = user.remnawave_id

            if not remnawave_id:
                # Строка была привязана к панели до апгрейда на 3.0.0: числового
                # id ей ещё не проставил бэкфил, но shortUuid панель знает.
                # Просто сдаться здесь нельзя — вызывающие этот метод (докупка
                # трафика и устройств, смена сквадов) результат не проверяют:
                # деньги списываются и коммитятся, а в панель не уезжает ничего.
                remnawave_id = await self._adopt_panel_id_for_update(db, subscription, user)

            if not remnawave_id:
                logger.error(
                    'RemnaWave id не найден для пользователя',
                    user_id=subscription.user_id,
                    subscription_id=subscription.id,
                )
                return None

            await db.flush((subscription, user))
            # Вызывающий мог загрузить объекты давно: перечитываем состояние, чтобы
            # старая синхронизация не затёрла только что закоммиченное продление.
            await db.refresh(subscription)
            await db.refresh(user)
            # Загружаем tariff заранее, чтобы избежать lazy loading в async контексте
            try:
                await db.refresh(subscription, ['tariff'])
            except Exception:
                logger.warning('Ignored error in update_remnawave_user', exc_info=True)
                # tariff может быть None или уже загружен

            # Снапшот traffic_limit_gb — источник истины для панели; если тариф
            # редактировали после покупки, снапшот протух и панель режет по
            # старому лимиту. Лечим из живого тарифа ДО пуша trafficLimitBytes.
            try:
                if subscription.tariff is not None:
                    from app.database.crud.subscription import reconcile_subscription_traffic_limit

                    await reconcile_subscription_traffic_limit(db, subscription, subscription.tariff)
            except Exception as _rec_err:
                logger.warning('Не удалось сверить лимит трафика с тарифом перед обновлением панели', error=_rec_err)

            current_time = datetime.now(UTC)
            # Определяем актуальный статус для отправки в RemnaWave
            # НЕ меняем статус подписки здесь - это задача scheduled job
            is_actually_active = is_subscription_live(user, subscription, now=current_time)

            # Логируем если статус и end_date не согласованы (для отладки)
            if (
                subscription.status in (SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIAL.value)
                and subscription.end_date <= current_time
            ):
                logger.warning(
                    '⚠️ update_remnawave_user: подписка имеет статус ACTIVE, но end_date <= now. Отправляем в RemnaWave как DISABLED, но НЕ меняем статус в БД.',
                    subscription_id=subscription.id,
                    end_date=subscription.end_date,
                    current_time=current_time,
                )

            user_tag = self._resolve_user_tag(subscription)

            # Определяем внешний сквад из тарифа
            ext_squad_uuid = subscription.tariff.external_squad_uuid if subscription.tariff else None

            async with self.get_api_client() as api:
                hwid_limit = resolve_hwid_device_limit_for_payload(subscription)

                # Сквады и внешний сквад уезжают только при явном sync_squads:
                # в рутинных обновлениях они уже назначены при создании подписки,
                # а пересылка устаревшего UUID даёт FK violation (A039).
                only_fields = {
                    'status',
                    'expire_at',
                    'traffic_limit_bytes',
                    'traffic_limit_strategy',
                    'telegram_id',
                    'email',
                    'description',
                    'tag',
                    'hwid_device_limit',
                }
                if sync_squads:
                    only_fields.update({'active_internal_squads', 'external_squad_uuid'})

                panel_payload = replace(
                    build_panel_payload(
                        user,
                        subscription,
                        user_tag=user_tag,
                        now=current_time,
                    ),
                    hwid_device_limit=hwid_limit,
                    external_squad_uuid=ext_squad_uuid,
                )
                # Аккаунт уже известен: адрес не перепроверяем, а «такого нет»
                # разбирает ветка ниже — у неё своя проверка, стоит ли
                # воскрешать подписку.
                updated_user = (
                    await push_subscription(
                        api,
                        user,
                        subscription,
                        db=db,
                        payload=panel_payload,
                        only_fields=only_fields,
                        identity=await self._known_panel_identity(api, user, subscription, remnawave_id),
                        create_if_missing=False,
                        recreate_on_missing=False,
                        reset_devices=False,
                        now=current_time,
                    )
                ).panel_user
                if updated_user is None:
                    raise RemnaWaveAPIError('Remnawave returned no user after subscription renewal update')

                if reset_traffic:
                    reset_id = user.remnawave_id
                    if reset_id:
                        await self._reset_user_traffic(
                            api,
                            reset_id,
                            user,
                            reset_reason,
                        )

                subscription.subscription_url = updated_user.subscription_url
                subscription.subscription_crypto_link = updated_user.happ_crypto_link
                await link_subscription_panel_identity(db, subscription, remnawave_id)
                await db.commit()

                status_text = 'активным' if is_actually_active else 'истёкшим'
                logger.info(
                    '✅ Обновлен RemnaWave пользователь со статусом',
                    remnawave_id=remnawave_id,
                    status_text=status_text,
                )
                strategy_name = settings.DEFAULT_TRAFFIC_RESET_STRATEGY
                logger.info('📊 Стратегия сброса трафика', strategy_name=strategy_name)
                return updated_user

        except asyncio.CancelledError:
            # ``CancelledError`` is not an Exception on supported Python
            # versions.  Timeouts must still release advisory/SQLite locks.
            await db.rollback()
            raise
        except RemnaWaveAPIError as e:
            if isinstance(e, DeviceLimitReconciliationError):
                await self._defer_device_limit_reconciliation(
                    db, subscription, user, action='update', reset_traffic=reset_traffic, reset_reason=reset_reason
                )
                logger.error('HWID limit reconciliation deferred', error=e)
                return None
            await db.rollback()
            if is_user_not_found_error(e):
                # Пользователя удалили из панели, пока подписка жива в боте, —
                # пересоздаём вместо ошибки (create-флоу сам найдёт/создаст
                # панель-юзера и сохранит новый id и ссылки в подписку).
                return await self.recreate_deleted_panel_user(
                    db, subscription, user=user, reset_traffic=reset_traffic, reset_reason=reset_reason
                )
            logger.error('Ошибка RemnaWave API', error=e)
            return None
        except Exception as e:
            await db.rollback()
            logger.error('Ошибка обновления RemnaWave пользователя', error=e)
            return None

    async def recreate_deleted_panel_user(
        self,
        db: AsyncSession,
        subscription: Subscription,
        *,
        user: User | None = None,
        reset_traffic: bool = False,
        reset_reason: str | None = None,
    ) -> RemnaWaveUser | None:
        """Пересоздаёт панель-юзера, удалённого из RemnaWave при живой подписке.

        Только для действующих подписок: пересоздавать DISABLED-юзера ради
        истёкшей подписки не нужно — админ удалил его намеренно.
        """
        # Сюда приходят после rollback: он экспирирует ORM-объекты, и первое же
        # чтение поля упало бы с MissingGreenlet — пересоздание не начиналось вовсе.
        await db.refresh(subscription)
        if user is not None:
            await db.refresh(user)

        is_actually_active = is_subscription_live(user, subscription)
        if not is_actually_active:
            logger.info(
                'Панель-юзер удалён из RemnaWave, подписка неактивна — пересоздание не требуется',
                subscription_id=subscription.id,
                user_id=subscription.user_id,
            )
            return None

        logger.warning(
            '⚠️ Панель-юзер удалён из RemnaWave при активной подписке — пересоздаём',
            subscription_id=subscription.id,
            user_id=subscription.user_id,
        )
        # users.remnawave_id перезапишет сам create-флоу.
        return await self.create_remnawave_user(
            db, subscription, reset_traffic=reset_traffic, reset_reason=reset_reason
        )

    @staticmethod
    def _format_user_log(user) -> str:
        """Форматирует идентификатор пользователя для логов."""
        if user.telegram_id:
            return f'user {user.telegram_id}'
        if user.email:
            return f'user {user.id} ({user.email})'
        return f'user {user.id}'

    async def _reset_user_traffic(
        self,
        api: RemnaWaveAPI,
        panel_user_id: int,
        user,  # User object вместо telegram_id
        reset_reason: str | None = None,
    ) -> None:
        if not panel_user_id:
            return

        try:
            await api.reset_user_traffic(panel_user_id)
            reason_text = f' ({reset_reason})' if reset_reason else ''
            logger.info(
                '🔄 Сброшен трафик RemnaWave', _format_user_log=self._format_user_log(user), reason_text=reason_text
            )
        except Exception as exc:
            logger.warning(
                '⚠️ Не удалось сбросить трафик RemnaWave', _format_user_log=self._format_user_log(user), error=exc
            )

    async def _known_panel_identity(self, api, user, subscription, panel_user_id: int) -> PanelIdentity:
        """Read a non-live account's date so its closing date goes in the first PATCH."""
        if not is_subscription_live(user, subscription):
            try:
                return PanelIdentity(panel_user=await api.get_user_by_id(panel_user_id), known_id=panel_user_id)
            except Exception as error:
                logger.warning(
                    'Не удалось прочитать дату панели перед гашением', panel_user_id=panel_user_id, error=error
                )
        return PanelIdentity(known_id=panel_user_id)

    async def extinguish_remnawave_expiry(
        self, db: AsyncSession, user: User, subscription: Subscription, panel_user_id: int | None
    ) -> bool:
        """Write an admin reset's status and expiry without creating a panel account."""
        if not panel_user_id:
            return False
        try:
            async with self.get_api_client() as api:
                result = await push_subscription(
                    api,
                    user,
                    subscription,
                    db=db,
                    identity=await self._known_panel_identity(api, user, subscription, panel_user_id),
                    only_fields={'status', 'expire_at'},
                    create_if_missing=False,
                    recreate_on_missing=False,
                    reset_devices=False,
                )
                return result.panel_user is not None and panel_date_is_closing(result.panel_user.expire_at)
        except Exception as error:
            logger.warning(
                'Не удалось погасить срок панели после обнуления', subscription_id=subscription.id, error=error
            )
            return False

    async def disable_remnawave_user(self, panel_user_id: int) -> bool:
        try:
            async with self.get_api_client() as api:
                await api.disable_user(coerce_panel_user_id(panel_user_id))
                logger.info('✅ Отключен RemnaWave пользователь', panel_user_id=panel_user_id)
                return True

        except Exception as e:
            error_msg = str(e).lower()
            # "User already disabled" - считаем успехом
            if 'already disabled' in error_msg:
                logger.info('✅ RemnaWave пользователь уже отключен', panel_user_id=panel_user_id)
                return True
            logger.error('Ошибка отключения RemnaWave пользователя', error=e)
            return False

    async def delete_remnawave_user(self, panel_user_id: int) -> bool:
        """Полное удаление пользователя из панели RemnaWave (хуки прекращаются)."""
        try:
            async with self.get_api_client() as api:
                await api.delete_user(panel_user_id)
                logger.info('🗑 Удалён RemnaWave пользователь', panel_user_id=panel_user_id)
                return True

        except Exception as e:
            error_msg = str(e).lower()
            if 'not found' in error_msg or 'not exist' in error_msg:
                logger.info('🗑 RemnaWave пользователь уже удалён', panel_user_id=panel_user_id)
                return True
            logger.error('Ошибка удаления RemnaWave пользователя', error=e, panel_user_id=panel_user_id)
            return False

    async def enable_remnawave_user(self, panel_user_id: int) -> bool:
        """Включить пользователя в RemnaWave (реактивация)."""
        try:
            async with self.get_api_client() as api:
                await api.enable_user(coerce_panel_user_id(panel_user_id))
                logger.info('✅ Включен RemnaWave пользователь', panel_user_id=panel_user_id)
                return True

        except Exception as e:
            error_msg = str(e).lower()
            # "User already enabled" - считаем успехом
            if 'already enabled' in error_msg:
                logger.info('✅ RemnaWave пользователь уже включен', panel_user_id=panel_user_id)
                return True
            logger.error('Ошибка включения RemnaWave пользователя', error=e)
            return False

    async def get_remnawave_squads(self) -> list[dict] | None:
        """Получить список internal squads из RemnaWave."""
        try:
            async with self.get_api_client() as api:
                squads = await api.get_internal_squads()
                # Преобразуем в формат для sync_with_remnawave
                result = []
                for squad in squads:
                    result.append(
                        {
                            'uuid': squad.uuid,
                            'name': squad.name,
                        }
                    )
                logger.info('✅ Получено серверов из RemnaWave', result_count=len(result))
                return result

        except Exception as e:
            logger.error('Ошибка получения серверов из RemnaWave', error=e)
            return None

    async def revoke_subscription(
        self, db: AsyncSession, subscription: Subscription
    ) -> SubscriptionReissueResult | None:
        try:
            user = await get_user_by_id(db, subscription.user_id)
            if not user:
                return None
            revoke_id = user.remnawave_id
            if not revoke_id:
                return None

            async with self.get_api_client() as api:
                updated_user = await api.revoke_user_subscription(revoke_id)
                if not updated_user.subscription_url:
                    logger.error('Panel reissue response has no subscription URL', subscription_id=subscription.id)
                    return None

                subscription.remnawave_short_uuid = updated_user.short_uuid
                subscription.subscription_url = updated_user.subscription_url
                subscription.subscription_crypto_link = updated_user.happ_crypto_link
                await db.commit()

                # Revoking credentials does not remove HWID registrations. The
                # new link is already durable even if device deletion fails.
                try:
                    devices_reset = await api.reset_user_devices(revoke_id)
                except Exception as reset_error:
                    logger.warning('Reissued link but failed to reset devices', error=str(reset_error))
                    devices_reset = False

                logger.info('✅ Обновлена ссылка подписки', _format_user_log=self._format_user_log(user))
                return SubscriptionReissueResult(updated_user.subscription_url, bool(devices_reset))

        except Exception as e:
            logger.error('Ошибка обновления ссылки подписки', error=e)
            return None

    async def get_subscription_info(self, short_uuid: str) -> dict | None:
        try:
            async with self.get_api_client() as api:
                info = await api.get_subscription_info(short_uuid)
                return info

        except Exception as e:
            logger.error('Ошибка получения информации о подписке', error=e)
            return None

    async def sync_subscription_usage(self, db: AsyncSession, subscription: Subscription) -> bool:
        try:
            user = await get_user_by_id(db, subscription.user_id)
            if not user:
                return False
            sync_id = user.remnawave_id
            if not sync_id:
                return False

            async with self.get_api_client() as api:
                remnawave_user = await api.get_user_by_id(sync_id)
                if not remnawave_user:
                    return False

                used_gb = self._bytes_to_gb(remnawave_user.used_traffic_bytes)
                subscription.traffic_used_gb = used_gb

                await db.commit()

                logger.debug('Синхронизирован трафик для подписки ГБ', subscription_id=subscription.id, used_gb=used_gb)
                return True

        except RemnaWaveAPIError as e:
            self.panel_failed = True
            logger.error('Ошибка синхронизации трафика', error=e)
            return False
        except Exception as e:
            logger.error('Ошибка синхронизации трафика', error=e)
            return False

    async def ensure_subscription_synced(
        self,
        db: AsyncSession,
        subscription: Subscription,
    ) -> tuple[bool, str | None]:
        """
        Проверяет и синхронизирует подписку с RemnaWave при необходимости.

        Если subscription_url отсутствует или данные не синхронизированы,
        пытается обновить/создать пользователя в RemnaWave.

        Returns:
            Tuple[bool, Optional[str]]: (успех, сообщение об ошибке)
        """
        # До панели: её сбой откатывает сессию, и подписка протухает — чтение subscription.id
        # в логе ошибки падало, а с ним весь экран «Моя подписка».
        subscription_id = subscription.id
        user = None
        try:
            user = await get_user_by_id(db, subscription.user_id)
            if not user:
                logger.error('Пользователь не найден для подписки', subscription_id=subscription_id)
                return False, 'user_not_found'

            # Проверяем, нужна ли синхронизация
            panel_user_id = user.remnawave_id
            needs_sync = not subscription.subscription_url or not panel_user_id

            if not needs_sync:
                # Проверяем, существует ли пользователь в RemnaWave
                try:
                    async with self.get_api_client() as api:
                        remnawave_user = await api.get_user_by_id(panel_user_id)
                        if not remnawave_user:
                            needs_sync = True
                            logger.warning(
                                'Пользователь не найден в RemnaWave, требуется синхронизация',
                                remnawave_id=panel_user_id,
                            )
                except Exception as check_error:
                    self.panel_failed = True
                    logger.warning('Не удалось проверить пользователя в RemnaWave', check_error=check_error)
                    # Продолжаем, возможно проблема временная

            if not needs_sync:
                return True, None

            logger.info(
                'Синхронизация подписки с RemnaWave',
                subscription_id=subscription.id,
                subscription_url=bool(subscription.subscription_url),
                remnawave_id=bool(panel_user_id),
            )

            # Пытаемся синхронизировать
            result = None
            if panel_user_id:
                # Пробуем обновить существующего пользователя
                result = await self.update_remnawave_user(
                    db,
                    subscription,
                    reset_traffic=False,
                )
                # Если update не удался (пользователь удалён из RemnaWave) — пробуем создать
                if not result:
                    logger.warning(
                        'Не удалось обновить пользователя в RemnaWave, пробуем создать заново',
                        remnawave_id=panel_user_id,
                    )
                    # Сбрасываем старый id, create_remnawave_user установит новый.
                    # Исторический uuid обнуляем ВМЕСТЕ с ним (до 3.0.0 так и было):
                    # иначе строка останется с uuid удалённого аккаунта при живом
                    # новом id, а бэкфилл строит по этой паре карту uuid -> id и
                    # выдаст grace-сессии мёртвого аккаунта живой, оплаченный.
                    user.remnawave_id = None
                    user.remnawave_uuid = None
                    result = await self.create_remnawave_user(
                        db,
                        subscription,
                        reset_traffic=False,
                    )
            else:
                # Создаём нового пользователя
                result = await self.create_remnawave_user(
                    db,
                    subscription,
                    reset_traffic=False,
                )

            if result:
                await db.refresh(subscription)
                await db.refresh(user)
                logger.info(
                    'Подписка успешно синхронизирована с RemnaWave',
                    subscription_id=subscription.id,
                )
                return True, None
            self.panel_failed = True
            await reload_after_panel_failure(db, subscription, user)
            logger.error('Не удалось синхронизировать подписку с RemnaWave', subscription_id=subscription_id)
            return False, 'sync_failed'

        except RemnaWaveAPIError as api_error:
            self.panel_failed = True
            await reload_after_panel_failure(db, subscription, user)
            logger.error(
                'Ошибка RemnaWave API при синхронизации подписки', subscription_id=subscription_id, api_error=api_error
            )
            return False, 'api_error'
        except Exception as e:
            await reload_after_panel_failure(db, subscription, user)
            logger.error('Ошибка синхронизации подписки', subscription_id=subscription_id, error=e)
            return False, 'unknown_error'

    async def validate_and_clean_subscription(self, db: AsyncSession, subscription: Subscription, user: User) -> bool:
        try:
            needs_cleanup = False
            # Отдельно от `needs_cleanup`: «панель не знает этот id» и «аккаунт
            # принадлежит другому человеку» — разные вещи. Перепривязка по
            # shortUuid допустима только для первого; для второго она означала бы
            # «оставить чужой аккаунт», ровно то, ради чего проверка и стоит.
            panel_lost_the_id = False
            foreign_short_uuid = False
            user_log = self._format_user_log(user)

            # Берём id пользователя, но при пустом — id самой
            # подписки: бэкфилл штатно оставляет строку пользователя
            # неразрешённой, заполнив при этом подписку, и без этого фолбэка
            # проверка считала бы аккаунт отсутствующим и стирала идентичность,
            # которую только что восстановили, — с пересозданием дубля в панели.
            check_id = user.remnawave_id or subscription.remnawave_id

            if check_id:
                try:
                    async with self.get_api_client() as api:
                        remnawave_user = await api.get_user_by_id(check_id)

                        if not remnawave_user:
                            logger.warning(
                                '⚠️ id не найден в панели',
                                user_log=user_log,
                                remnawave_id=check_id,
                            )
                            needs_cleanup = True
                            panel_lost_the_id = True
                        elif (
                            user.telegram_id
                            and remnawave_user.telegram_id
                            and remnawave_user.telegram_id != user.telegram_id
                        ):
                            logger.warning(
                                '⚠️ Несоответствие telegram_id для panel',
                                user_log=user_log,
                                telegram_id=remnawave_user.telegram_id,
                            )
                            needs_cleanup = True
                except Exception as api_error:
                    logger.error('❌ Ошибка проверки пользователя в панели', api_error=api_error)
                    # A timeout/5xx is not proof that the panel user vanished.
                    # Preserve the panel id and abort so a retry cannot create a
                    # duplicate Remnawave account.
                    return False

            # Гейт по `panel_lost_the_id`, а НЕ по «не было check_id»: строка с
            # протухшим числовым id (панель его не знает) иначе теряла последний
            # шанс — очистка стирала единственный точный ключ восстановления.
            # И НЕ по `needs_cleanup`: тот же флаг ставит несовпадение владельца,
            # а для него перепривязка недопустима.
            if subscription.remnawave_short_uuid and (panel_lost_the_id or not check_id):
                # После апгрейда на 3.0.0 у той же комбинации есть второе прочтение: строка была привязана к
                # панели, а числовой id ей ещё не проставил бэкфил. Разница принципиальна — очистка стирает
                # remnawave_short_uuid, единственный точный ключ восстановления связи. Поэтому решает не
                # догадка, а сама панель.
                try:
                    async with self.get_api_client() as api:
                        panel_user = await api.get_user_by_short_uuid(subscription.remnawave_short_uuid)
                except Exception as api_error:
                    logger.error(
                        '❌ Не удалось проверить short_uuid в панели — очистку не делаем',
                        subscription_id=subscription.id,
                        api_error=api_error,
                    )
                    return False

                panel_telegram_id = getattr(panel_user, 'telegram_id', None) if panel_user is not None else None
                if (
                    panel_user is not None
                    and user.telegram_id
                    and panel_telegram_id
                    and panel_telegram_id != user.telegram_id
                ):
                    # Нашли по shortUuid, но аккаунт чужой — привязывать нельзя.
                    logger.warning(
                        '⚠️ Аккаунт по short_uuid принадлежит другому telegram_id — не привязываем',
                        subscription_id=subscription.id,
                        panel_telegram_id=panel_telegram_id,
                    )
                    panel_user = None
                    needs_cleanup = True
                    foreign_short_uuid = True

                if panel_user is not None:
                    logger.info(
                        '🔗 Панельный пользователь опознан по short_uuid, проставляем remnawave_id',
                        subscription_id=subscription.id,
                        remnawave_id=panel_user.id,
                    )
                    # Та же защита частично-уникального индекса, что и в
                    # `create_remnawave_user`: соседняя подписка того же человека
                    # штатно держит этот аккаунт после бэкфила, и безусловная
                    # запись падала бы здесь на IntegrityError.
                    if await self._panel_id_is_free_for(db, subscription, panel_user.id):
                        subscription.remnawave_id = panel_user.id
                    else:
                        logger.warning(
                            '⚠️ Панельный id уже закреплён за другой подпиской — адресуем через пользователя',
                            subscription_id=subscription.id,
                            remnawave_id=panel_user.id,
                        )
                    if not user.remnawave_id:
                        user.remnawave_id = panel_user.id
                    await db.flush((subscription, user))
                    return True

                if foreign_short_uuid:
                    logger.warning('⚠️ short_uuid ведёт на аккаунт другого пользователя — связь рвём')
                else:
                    logger.warning('⚠️ У подписки есть short_uuid, но панель его не знает')
                needs_cleanup = True

            if needs_cleanup:
                logger.info('🧹 Очищаем мусорные данные подписки', user_log=user_log)

                subscription.remnawave_short_uuid = None
                subscription.remnawave_id = None
                # Вместе с id обнуляем и исторический uuid — иначе строка несёт
                # uuid удалённого аккаунта, а следующий id будет уже от нового:
                # бэкфилл строит по этой паре карту и свяжет grace-сессию
                # мёртвого аккаунта с живым. До 3.0.0 uuid чистился здесь же.
                subscription.remnawave_uuid = None
                subscription.subscription_url = ''
                subscription.subscription_crypto_link = ''

                user.remnawave_id = None
                user.remnawave_uuid = None

                # Keep cleanup in the caller's transaction.  Committing here
                # could burn a coupon/payment if the following panel create
                # fails; create_remnawave_user commits only after API success.
                await db.flush((subscription, user))
                logger.info('✅ Мусорные данные подготовлены к очистке', user_log=user_log)

            return True

        except Exception as e:
            logger.error('❌ Ошибка валидации подписки', _format_user_log=self._format_user_log(user), error=e)
            await db.rollback()
            return False

    def _gb_to_bytes(self, gb: int | None) -> int:
        if not gb:  # None or 0
            return 0
        return gb * 1024 * 1024 * 1024

    def _bytes_to_gb(self, bytes_value: int) -> float:
        if bytes_value == 0:
            return 0.0
        return bytes_value / (1024 * 1024 * 1024)


async def reset_subscription_with_panel(db, user: User, subscription: Subscription) -> dict:
    """Обнулить подписку «как будто не оформляли» и снять доступ в панели RemnaWave,
    НЕ удаляя пользователя из БД (тикеты и аккаунт остаются).

    Панельного пользователя ОТКЛЮЧАЕМ (disable), а не удаляем — обратимо. Дальше юзер
    может купить тариф с нуля. Возвращает ``{'panel_disabled': bool, 'panel_user_id': int|None}``.
    """
    from app.database.crud.subscription import reset_subscription

    # Fallback на user.remnawave_id: панель адресуется через человека.
    panel_user_id = subscription.remnawave_id or user.remnawave_id

    panel_disabled = False
    if panel_user_id:
        try:
            panel_disabled = await SubscriptionService().disable_remnawave_user(panel_user_id)
        except Exception as e:
            logger.warning('Не удалось отключить пользователя в RemnaWave при обнулении подписки', error=e)
    else:
        logger.warning(
            'Обнуление подписки: панельный id не найден, отключение в панели пропущено',
            subscription_id=subscription.id,
        )

    await reset_subscription(db, subscription)
    expiry_extinguished = await SubscriptionService().extinguish_remnawave_expiry(db, user, subscription, panel_user_id)
    return {
        'panel_disabled': panel_disabled,
        'panel_user_id': panel_user_id,
        'panel_expiry_extinguished': expiry_extinguished,
    }
