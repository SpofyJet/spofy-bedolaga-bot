"""Автобэкап снимает базу pg_dump-ом, а не ORM-выгрузкой в JSON.

Без pg_dump в образе BackupService уходит в ORM-выгрузку: держит всю базу в
памяти бота (3,4 ГБ из 7 на проде; 15.11.2026 вместе с другой нагрузкой это
кончилось OOM) и пропускает таблицы, которых нет в его списке моделей (33 из
105, среди них platega_subscriptions). pg_dump снимает всё, отдельным процессом.

Инварианты:
1. major-версия клиента в образе = major сервера в compose: pg_dump 17 базу 18
   не снимет, и бэкап молча перестанет создаваться;
2. дамп не включает строки журнала мониторинга без BACKUP_INCLUDE_LOGS (как ORM);
3. восстановление идёт одной транзакцией с остановкой на первой ошибке: либо
   база восстановлена целиком, либо осталась как была.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from app.services import backup_service as bs


REPO_ROOT = Path(__file__).resolve().parent.parent


def _server_major() -> str:
    compose = yaml.safe_load((REPO_ROOT / 'docker-compose.yml').read_text(encoding='utf-8'))
    tag = compose['services']['postgres']['image'].split('@', 1)[0]
    match = re.fullmatch(r'postgres:(\d+)(?:[.-].*)?', tag)
    assert match, tag
    return match.group(1)


def test_image_ships_pg_client_of_the_server_major() -> None:
    dockerfile = (REPO_ROOT / 'Dockerfile').read_text(encoding='utf-8')
    major = _server_major()

    assert f'postgresql-client-{major}' in dockerfile
    path_lines = [line for line in dockerfile.splitlines() if line.startswith('ENV PATH=')]
    assert path_lines and all(f'/usr/lib/postgresql/{major}/bin' in line for line in path_lines)
    assert 'COPY docker/postgres/pgdg-apt.asc' in dockerfile
    assert (REPO_ROOT / 'docker' / 'postgres' / 'pgdg-apt.asc').read_text().startswith(
        '-----BEGIN PGP PUBLIC KEY BLOCK-----'
    )


def _fake_process(returncode: int = 0, stderr: bytes = b'') -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(b'', stderr))
    return proc


@pytest.mark.asyncio
@pytest.mark.parametrize('include_logs', [False, True])
async def test_dump_skips_monitoring_rows_only_without_logs(tmp_path: Path, include_logs: bool) -> None:
    service = bs.BackupService.__new__(bs.BackupService)
    spawn = AsyncMock(return_value=_fake_process())

    with patch.object(bs.asyncio, 'create_subprocess_exec', spawn):
        await service._dump_postgres(tmp_path / 'database.sql', '/usr/bin/pg_dump', include_logs=include_logs)

    args = list(spawn.call_args.args)
    assert args[0] == '/usr/bin/pg_dump'
    assert '--format=plain' in args
    assert any(a.startswith('--lock-wait-timeout=') for a in args)
    excluded = f'--exclude-table-data={bs.MonitoringLog.__tablename__}'
    assert (excluded in args) is (not include_logs)
    assert args[-1] == bs.settings.POSTGRES_DB


@pytest.mark.asyncio
@pytest.mark.parametrize('clear_existing', [False, True])
async def test_restore_is_one_transaction_that_stops_on_error(tmp_path: Path, clear_existing: bool) -> None:
    dump = tmp_path / 'database.sql'
    dump.write_text('SELECT 1;\n', encoding='utf-8')
    service = bs.BackupService.__new__(bs.BackupService)
    spawn = AsyncMock(return_value=_fake_process())

    with (
        patch.object(service, '_resolve_command_path', return_value='/usr/bin/psql'),
        patch.object(bs.asyncio, 'create_subprocess_exec', spawn),
    ):
        await service._restore_postgres(dump, clear_existing)

    # Один вызов psql: очистка схемы и заливка внутри одной транзакции.
    assert spawn.call_count == 1
    args = list(spawn.call_args.args)
    assert {'--single-transaction', 'ON_ERROR_STOP=1', '--no-psqlrc'} <= set(args)
    assert args[args.index('-f') + 1] == str(dump)
    drop = [a for a in args if 'DROP SCHEMA public CASCADE' in a]
    assert bool(drop) is clear_existing
    if clear_existing:
        assert args.index(drop[0]) < args.index('-f')


@pytest.mark.asyncio
async def test_restore_reports_psql_failure(tmp_path: Path) -> None:
    dump = tmp_path / 'database.sql'
    dump.write_text('SELECT 1;\n', encoding='utf-8')
    service = bs.BackupService.__new__(bs.BackupService)
    spawn = AsyncMock(return_value=_fake_process(returncode=3, stderr=b'ERROR: relation exists'))

    with (
        patch.object(service, '_resolve_command_path', return_value='/usr/bin/psql'),
        patch.object(bs.asyncio, 'create_subprocess_exec', spawn),
        pytest.raises(RuntimeError, match='relation exists'),
    ):
        await service._restore_postgres(dump, clear_existing=True)
