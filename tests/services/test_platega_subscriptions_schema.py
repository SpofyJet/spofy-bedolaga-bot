"""Схема platega_subscriptions: таблица осталась после удаления СБП-автопродления.

Удаление подписки не стирает историю привязок (SET NULL, миграция 0140).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from app.database.models import PlategaSubscription


def test_model_table_and_columns():
    assert PlategaSubscription.__tablename__ == 'platega_subscriptions'
    cols = set(PlategaSubscription.__table__.columns.keys())
    assert {'platega_subscription_id', 'interval', 'charge_days', 'amount_kopeks', 'status'} <= cols


def test_model_fk_is_set_null_and_nullable():
    column = PlategaSubscription.__table__.c.subscription_id
    assert column.nullable is True
    (fk,) = column.foreign_keys
    assert fk.ondelete == 'SET NULL'


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'm0140', Path('migrations/alembic/versions/0140_platega_sub_fk_set_null.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0140_upgrade_downgrade_idempotent():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    module = _load_migration()
    assert (module.revision, module.down_revision) == ('0140', '0139')

    engine = sa.create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(sa.text('CREATE TABLE subscriptions (id INTEGER PRIMARY KEY)'))
        conn.execute(
            sa.text(
                'CREATE TABLE platega_subscriptions (id INTEGER PRIMARY KEY, subscription_id INTEGER NOT NULL, '
                'status VARCHAR(20), CONSTRAINT platega_subscriptions_subscription_id_fkey FOREIGN KEY '
                '(subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE)'
            )
        )
        conn.execute(sa.text('INSERT INTO subscriptions VALUES (1)'))
        conn.execute(sa.text("INSERT INTO platega_subscriptions VALUES (1, 1, 'ACTIVE')"))

        def state():
            inspector = sa.inspect(conn)
            fks = [fk for fk in inspector.get_foreign_keys('platega_subscriptions')]
            column = next(c for c in inspector.get_columns('platega_subscriptions') if c['name'] == 'subscription_id')
            return [str(fk['options'].get('ondelete')).upper() for fk in fks], bool(column['nullable'])

        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()
            assert state() == (['SET NULL'], True)
            module.upgrade()  # повторный прогон — без изменений и без ошибок
            assert state() == (['SET NULL'], True)

        conn.execute(sa.text("INSERT INTO platega_subscriptions VALUES (2, NULL, 'ACTIVE')"))
        assert conn.execute(sa.text('SELECT count(*) FROM platega_subscriptions')).scalar() == 2

        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()
            assert state() == (['CASCADE'], False)
            module.downgrade()
            assert state() == (['CASCADE'], False)
        # Строка-сирота удалена (её снёс бы CASCADE), живая привязка осталась.
        assert conn.execute(sa.text('SELECT id FROM platega_subscriptions')).scalars().all() == [1]
