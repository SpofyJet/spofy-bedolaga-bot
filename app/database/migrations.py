"""Programmatic Alembic migration runner for bot startup."""

from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _PROJECT_ROOT / 'alembic.ini'


def _get_alembic_config() -> Config:
    """Build Alembic Config pointing at the project root."""
    from app.config import settings

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option('sqlalchemy.url', settings.get_database_url())
    return cfg


async def _detect_db_state() -> str:
    """Detect database state: 'fresh', 'legacy', or 'managed'.

    - fresh: no tables at all — brand new database
    - legacy: has tables but no alembic_version (transition from universal_migration)
    - managed: has alembic_version — already managed by Alembic
    """
    from app.database.database import engine

    async with engine.connect() as conn:
        has_alembic = await conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table('alembic_version'))
        if has_alembic:
            return 'managed'
        has_users = await conn.run_sync(lambda sync_conn: inspect(sync_conn).has_table('users'))
        return 'legacy' if has_users else 'fresh'


_INITIAL_REVISION = '0001'


async def _bootstrap_fresh_db() -> None:
    """Bootstrap a fresh database: create all tables from models and stamp at head.

    On a fresh DB, running all migrations sequentially would fail because
    migration 0001 uses Base.metadata.create_all() which creates ALL tables
    from the current models.py (including columns/constraints/indexes added
    by later migrations), and then those later migrations try to re-create
    the same objects.  Instead, we create the full schema directly and stamp
    the migration history at HEAD so Alembic considers all migrations applied.
    """
    from app.database.database import engine
    from app.database.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info('Свежая БД: все таблицы созданы из моделей')


async def _ensure_runtime_schema_guards() -> None:
    """Install DDL guards that ``metadata.create_all`` cannot express."""
    from app.database.database import engine

    async with engine.begin() as conn:
        dialect = conn.dialect.name
        if dialect == 'postgresql':
            await conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION guard_open_grace_subscription_delete()
                    RETURNS trigger AS $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM grace_access_sessions
                            WHERE subscription_id = OLD.id
                              AND state IN ('pending', 'active', 'restoring')
                        ) THEN
                            RAISE EXCEPTION 'subscription has an open grace-access session'
                                USING ERRCODE = '23503';
                        END IF;
                        RETURN OLD;
                    END;
                    $$ LANGUAGE plpgsql
                    """
                )
            )
            # CREATE TRIGGER берёт ACCESS EXCLUSIVE на subscriptions — на каждом
            # старте это лишний lock-риск (боот может зависнуть об чужую
            # транзакцию). Создаём только при отсутствии; тело логики живёт в
            # функции выше, которую CREATE OR REPLACE обновляет без такого лока.
            trigger_exists = (
                await conn.execute(
                    text(
                        """
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'trg_guard_open_grace_subscription_delete'
                          AND tgrelid = 'subscriptions'::regclass
                          AND NOT tgisinternal
                        """
                    )
                )
            ).scalar() is not None
            if not trigger_exists:
                await conn.execute(
                    text(
                        """
                        CREATE TRIGGER trg_guard_open_grace_subscription_delete
                        BEFORE DELETE ON subscriptions
                        FOR EACH ROW EXECUTE FUNCTION guard_open_grace_subscription_delete()
                        """
                    )
                )
        elif dialect == 'sqlite':
            await conn.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_guard_open_grace_subscription_delete
                    BEFORE DELETE ON subscriptions
                    FOR EACH ROW
                    WHEN EXISTS (
                        SELECT 1 FROM grace_access_sessions
                        WHERE subscription_id = OLD.id
                          AND state IN ('pending', 'active', 'restoring')
                    )
                    BEGIN
                        SELECT RAISE(ABORT, 'subscription has an open grace-access session');
                    END
                    """
                )
            )


async def _ensure_mailing_schema() -> None:
    """Кольцо таблиц рассыльщика (ma_*) — идемпотентно, сырым SQL.

    Рассылка живёт своим контуром в app/mailing/ (свой контейнер, БД, воркеры
    очередей). Кольцо создаётся по прежней схеме, чтобы два alembic-дерева
    никогда не пересекались и раскатка оставалась идемпотентной: CREATE IF NOT
    EXISTS для всех объектов, повторный прогон — no-op.
    """
    from app.database.database import engine

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ma_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(128) NOT NULL UNIQUE,
                    value TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS ma_users (
                    user_id BIGINT PRIMARY KEY,
                    tg_user_id BIGINT,
                    username VARCHAR(64),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    language VARCHAR(16),
                    is_bot BOOLEAN NOT NULL DEFAULT FALSE,
                    is_premium BOOLEAN,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    deleted_at TIMESTAMPTZ,
                    ma_settings_id INTEGER REFERENCES ma_settings(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ma_chats (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    chat_type VARCHAR(32) NOT NULL,
                    title VARCHAR(512),
                    username VARCHAR(64),
                    member_count INTEGER,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    language VARCHAR(16),
                    last_activity_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    deleted_at TIMESTAMPTZ,
                    ma_settings_id INTEGER REFERENCES ma_settings(id) ON DELETE CASCADE,
                    UNIQUE(chat_id, chat_type)
                );

                CREATE TABLE IF NOT EXISTS ma_mailing_lists (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    deleted_at TIMESTAMPTZ,
                    ma_settings_id INTEGER REFERENCES ma_settings(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ma_campaigns (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    status VARCHAR(32) NOT NULL DEFAULT 'draft',
                    scheduled_at TIMESTAMPTZ,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    total_recipients INTEGER NOT NULL DEFAULT 0,
                    sent_count INTEGER NOT NULL DEFAULT 0,
                    delivered_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    blocked_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    deleted_at TIMESTAMPTZ,
                    ma_mailing_list_id INTEGER REFERENCES ma_mailing_lists(id) ON DELETE SET NULL,
                    ma_settings_id INTEGER REFERENCES ma_settings(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS ma_campaign_recipients (
                    id SERIAL PRIMARY KEY,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    sent_at TIMESTAMPTZ,
                    delivered_at TIMESTAMPTZ,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    ma_campaign_id INTEGER NOT NULL REFERENCES ma_campaigns(id) ON DELETE CASCADE,
                    ma_user_id INTEGER REFERENCES ma_users(id) ON DELETE CASCADE,
                    ma_chat_id INTEGER REFERENCES ma_chats(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_ma_campaign_recipients_campaign
                    ON ma_campaign_recipients (ma_campaign_id, status);
                CREATE INDEX IF NOT EXISTS ix_ma_campaign_recipients_user
                    ON ma_campaign_recipients (ma_user_id);

                CREATE TABLE IF NOT EXISTS ma_queue_jobs (
                    id SERIAL PRIMARY KEY,
                    job_type VARCHAR(64) NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    processed_at TIMESTAMPTZ,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    ma_campaign_id INTEGER REFERENCES ma_campaigns(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_ma_queue_jobs_status ON ma_queue_jobs (status, run_at);

                CREATE TABLE IF NOT EXISTS ma_message_logs (
                    id SERIAL PRIMARY KEY,
                    direction VARCHAR(16) NOT NULL DEFAULT 'outgoing',
                    message_type VARCHAR(64),
                    status VARCHAR(32),
                    error_message TEXT,
                    sent_at TIMESTAMPTZ,
                    delivered_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    ma_user_id INTEGER REFERENCES ma_users(id) ON DELETE SET NULL,
                    ma_chat_id INTEGER REFERENCES ma_chats(id) ON DELETE SET NULL,
                    ma_campaign_id INTEGER REFERENCES ma_campaigns(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS ix_ma_message_logs_campaign
                    ON ma_message_logs (ma_campaign_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_ma_message_logs_user
                    ON ma_message_logs (ma_user_id, created_at);

                CREATE TABLE IF NOT EXISTS ma_stats (
                    id SERIAL PRIMARY KEY,
                    stat_date DATE NOT NULL,
                    stat_type VARCHAR(64) NOT NULL,
                    total_sent INTEGER NOT NULL DEFAULT 0,
                    total_delivered INTEGER NOT NULL DEFAULT 0,
                    total_failed INTEGER NOT NULL DEFAULT 0,
                    total_blocked INTEGER NOT NULL DEFAULT 0,
                    active_users INTEGER NOT NULL DEFAULT 0,
                    active_chats INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    ma_settings_id INTEGER REFERENCES ma_settings(id) ON DELETE CASCADE,
                    UNIQUE(stat_date, stat_type)
                );
                """
            )
        )
    logger.info('Схема рассыльщика (ma_*) проверена/создана')


# Spofy: до v5.0.0 форк жил на своей цепочке ревизий — 0099 (xrocket) и 0100
# (вечные тарифы) вклинились после 0098, а апстримные 0099–0104 и 0120–0125
# были перенесены под номерами 0101–0113. Номера совпадают с апстримными, но
# значат другое: оставь базу на «0113», и Alembic решит, что апстримные
# 0105–0113 (рефералка по уровням, email-очередь, TabPay…) уже применены.
# Поэтому базу форка переставляем на последнюю общую точку — апстримную 0104;
# дальше идемпотентные миграции 0105–0131 докатывают недостающее и пропускают
# уже сделанное, а 0132/0133 — те же xrocket и вечные тарифы, тоже идемпотентные.
_SPOFY_FORK_REVISION_MAP = {
    '0099': '0098',
    '0100': '0098',
    '0101': '0099',
    '0102': '0100',
    '0103': '0101',
    '0104': '0102',
    '0105': '0103',
    '0106': '0104',
    '0107': '0104',
    '0108': '0104',
    '0109': '0104',
    '0110': '0104',
    '0111': '0104',
    '0112': '0104',
    '0113': '0104',
}


async def _reconcile_spofy_fork_chain() -> None:
    """Re-stamp a DB from the pre-v5 Spofy fork chain onto the upstream chain."""
    from app.database.database import engine

    async with engine.connect() as conn:
        tables = set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))
        if 'xrocket_payments' not in tables or 'tabpay_payments' in tables:
            return
        current = (await conn.execute(text('SELECT version_num FROM alembic_version'))).scalar_one_or_none()

    target = _SPOFY_FORK_REVISION_MAP.get(current or '')
    if target is None:
        return
    logger.warning(
        'База на цепочке миграций старого форка Spofy — переставляю на апстримную',
        fork_revision=current,
        upstream_revision=target,
    )
    await _stamp_alembic_revision(target)


async def run_alembic_upgrade() -> None:
    """Run ``alembic upgrade head``, handling fresh and legacy databases."""
    import asyncio

    db_state = await _detect_db_state()

    if db_state == 'fresh':
        logger.warning('Обнаружена пустая БД — создание схемы из моделей + stamp head')
        await _bootstrap_fresh_db()
        await _ensure_runtime_schema_guards()
        await _ensure_mailing_schema()
        await _stamp_alembic_revision('head')
        return

    if db_state == 'legacy':
        logger.warning(
            'Обнаружена существующая БД без alembic_version — автоматический stamp 0001 (переход с universal_migration)'
        )
        await _stamp_alembic_revision(_INITIAL_REVISION)

    if db_state == 'managed':
        await _reconcile_spofy_fork_chain()

    cfg = _get_alembic_config()
    loop = asyncio.get_running_loop()
    # run_in_executor offloads to a thread where env.py can safely
    # call asyncio.run() to create its own event loop.
    await loop.run_in_executor(None, command.upgrade, cfg, 'head')
    await _ensure_runtime_schema_guards()
    await _ensure_mailing_schema()
    logger.info('Alembic миграции применены')


async def stamp_alembic_head() -> None:
    """Stamp the DB as being at head without running migrations (for existing DBs)."""
    await _stamp_alembic_revision('head')


async def _stamp_alembic_revision(revision: str) -> None:
    """Stamp the DB at a specific revision without running migrations."""
    import asyncio

    cfg = _get_alembic_config()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, command.stamp, cfg, revision)
    logger.info('Alembic: база отмечена как актуальная', revision=revision)
