"""Загрузчик миграций для тестов.

Общий хелпер `_load` — в апстриме он живёт в test_retired_gateway_migration_postgres.py,
но та проверка завязана на чужую для Spofy миграцию (0132_retire_paypear), поэтому
хелпер вынесен сюда, а новые тесты миграций импортируют его из этого модуля.
"""

import importlib.util
from pathlib import Path


def _load(filename):
    spec = importlib.util.spec_from_file_location(
        'migration_under_test', Path('migrations/alembic/versions') / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
