import time
from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.config import settings


logger = structlog.get_logger(__name__)

# ============================================================================
# PRODUCTION-GRADE CONNECTION POOLING
# ============================================================================


def _is_sqlite_url(url: str) -> bool:
    """Проверка на SQLite URL (поддерживает sqlite:// и sqlite+aiosqlite://)"""
    return url.startswith('sqlite') or ':memory:' in url


def _build_pool_kwargs(is_sqlite: bool) -> dict:
    """Собрать kwargs пула SQLAlchemy для engine.

    Для SQLite используется ``NullPool`` (без пулинга), поэтому kwargs пустые.
    Для PostgreSQL размер пула / overflow / timeout читаются из настроек
    (env-настраиваемые: масштабирование пула под нагрузку без пересборки образа,
    см. DATABASE_POOL_SIZE / DATABASE_MAX_OVERFLOW / DATABASE_POOL_TIMEOUT).
    recycle / pre_ping / reset_on_return остаются безопасными prod-дефолтами.
    """
    if is_sqlite:
        return {}
    return {
        'pool_size': settings.DATABASE_POOL_SIZE,  # держим ниже max_connections PostgreSQL
        'max_overflow': settings.DATABASE_MAX_OVERFLOW,  # доп. соединения сверх pool_size при всплесках
        'pool_timeout': settings.DATABASE_POOL_TIMEOUT,  # сек ожидания свободного соединения до TimeoutError
        'pool_recycle': 1800,  # 30 мин для более быстрого recycling
        'pool_pre_ping': True,
        # Агрессивная очистка мертвых соединений
        'pool_reset_on_return': 'rollback',
    }


DATABASE_URL = settings.get_database_url()
IS_SQLITE = _is_sqlite_url(DATABASE_URL)

poolclass = NullPool if IS_SQLITE else AsyncAdaptedQueuePool
pool_kwargs = _build_pool_kwargs(IS_SQLITE)

# ============================================================================
# ENGINE WITH ADVANCED OPTIMIZATIONS
# ============================================================================

# PostgreSQL-специфичные connect_args
_pg_connect_args = {
    'server_settings': {
        'application_name': 'remnawave_bot',
        'jit': 'on',
        'statement_timeout': '60000',  # 60 секунд
        'idle_in_transaction_session_timeout': '300000',  # 5 минут
    },
    'command_timeout': 30,  # Уменьшен с 60, быстрее обнаруживать зависшие запросы
    'timeout': 10,  # Уменьшен с 60, быстрый провал при недоступности PostgreSQL
}
_sqlite_connect_args = {
    # Panel-sync leases deliberately hold a SQLite writer transaction
    # across one HTTP request.  Let competing local work wait instead of
    # failing with a short default "database is locked" timeout.
    'timeout': 60,
}

engine = create_async_engine(
    DATABASE_URL,
    poolclass=poolclass,
    echo='debug' if settings.DEBUG else False,
    future=True,
    # Кеш скомпилированных запросов (правильное размещение)
    query_cache_size=500,
    connect_args=_pg_connect_args if not IS_SQLITE else _sqlite_connect_args,
    execution_options={
        'isolation_level': 'READ COMMITTED',
    },
    **pool_kwargs,
)

if IS_SQLITE:

    @event.listens_for(engine.sync_engine, 'connect')
    def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        """Enable concurrency settings on every SQLite connection.

        PRAGMA foreign_keys здесь сознательно НЕ включаем: у существующих
        SQLite-инсталляций могут быть orphan-строки из старых версий схемы,
        и глобальный флип enforcement ломал бы их DELETE/UPDATE. Защита
        grace-снимка держится на DB-триггере, а не на FK.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute('PRAGMA busy_timeout=60000')
            cursor.execute('PRAGMA journal_mode=WAL')
        finally:
            cursor.close()

# ============================================================================
# SESSION FACTORY WITH OPTIMIZATIONS
# ============================================================================

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,  # Критично для производительности
    autocommit=False,
)

# ============================================================================
# RETRY LOGIC FOR DATABASE OPERATIONS
# ============================================================================


# ============================================================================
# QUERY PERFORMANCE MONITORING
# ============================================================================

if settings.DEBUG:

    @event.listens_for(Engine, 'before_cursor_execute')
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault('query_start_time', []).append(time.time())
        logger.debug('🔍 Executing query: ...', statement=statement[:100])

    @event.listens_for(Engine, 'after_cursor_execute')
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total = time.time() - conn.info['query_start_time'].pop(-1)
        if total > 0.1:  # Логируем медленные запросы > 100ms
            logger.warning('🐌 Slow query (s): ...', total=round(total, 3), statement=statement[:100])
        else:
            logger.debug('⚡ Query executed in', total=round(total, 3))

# ============================================================================
# SESSION DEPENDENCY FOR FASTAPI/AIOGRAM
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Стандартная dependency для FastAPI"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ============================================================================
# INITIALIZATION AND CLEANUP
# ============================================================================


# ============================================================================
# SEQUENCE SYNCHRONIZATION (after DB restores)
# ============================================================================


def _quote_ident(name: str) -> str:
    """Quote a PostgreSQL identifier to prevent SQL injection."""
    return '"' + name.replace('"', '""') + '"'


async def sync_postgres_sequences() -> bool:
    """Ensure PostgreSQL sequences match the current max values after restores."""
    if IS_SQLITE:
        logger.debug('Пропускаем синхронизацию последовательностей: SQLite')
        return True

    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT
                        cols.table_schema,
                        cols.table_name,
                        cols.column_name,
                        pg_get_serial_sequence(
                            format('%I.%I', cols.table_schema, cols.table_name),
                            cols.column_name
                        ) AS sequence_path
                    FROM information_schema.columns AS cols
                    WHERE cols.column_default LIKE 'nextval(%'
                      AND cols.table_schema NOT IN ('pg_catalog', 'information_schema')
                    """
                )
            )

            sequences = result.fetchall()

            if not sequences:
                logger.info('Не найдено последовательностей PostgreSQL для синхронизации')
                return True

            for table_schema, table_name, column_name, sequence_path in sequences:
                if not sequence_path:
                    continue

                q_col = _quote_ident(column_name)
                q_schema = _quote_ident(table_schema)
                q_table = _quote_ident(table_name)

                max_result = await conn.execute(text(f'SELECT COALESCE(MAX({q_col}), 0) FROM {q_schema}.{q_table}'))
                max_value = max_result.scalar() or 0

                # pg_get_serial_sequence returns e.g. '"public"."users_id_seq"'.
                # Split on '"."' to handle quoted identifiers that may contain dots.
                if '"."' in sequence_path:
                    seq_schema, seq_name = sequence_path.split('"."', 1)
                    seq_schema = seq_schema.strip('"')
                    seq_name = seq_name.strip('"')
                else:
                    parts = sequence_path.split('.')
                    if len(parts) == 2:
                        seq_schema, seq_name = parts
                    else:
                        seq_schema, seq_name = 'public', parts[-1]
                q_seq_schema = _quote_ident(seq_schema)
                q_seq_name = _quote_ident(seq_name)
                current_result = await conn.execute(
                    text(f'SELECT last_value, is_called FROM {q_seq_schema}.{q_seq_name}')
                )
                current_row = current_result.fetchone()

                if current_row:
                    current_last, is_called = current_row
                    current_next = current_last + 1 if is_called else current_last
                    if current_next > max_value:
                        continue

                await conn.execute(
                    text(
                        """
                        SELECT setval(:sequence_name, :new_value, TRUE)
                        """
                    ),
                    {'sequence_name': sequence_path, 'new_value': max_value},
                )
                logger.info(
                    'Последовательность синхронизирована',
                    sequence_path=sequence_path,
                    max_value=max_value,
                    next_id=max_value + 1,
                )

        return True

    except Exception as error:
        logger.error('Ошибка синхронизации последовательностей PostgreSQL', error=error)
        return False


# ============================================================================
# CONNECTION POOL METRICS (для мониторинга)
# ============================================================================


def _pool_counters(pool):
    """Return basic pool counters or ``None`` when unsupported."""

    required_methods = ('size', 'checkedin', 'checkedout', 'overflow')

    for method_name in required_methods:
        method = getattr(pool, method_name, None)
        if method is None or not callable(method):
            return None

    size = pool.size()
    checked_in = pool.checkedin()
    checked_out = pool.checkedout()
    overflow = pool.overflow()

    total_connections = size + overflow

    return {
        'size': size,
        'checked_in': checked_in,
        'checked_out': checked_out,
        'overflow': overflow,
        'total_connections': total_connections,
        'utilization_percent': (checked_out / total_connections * 100) if total_connections else 0.0,
    }
