"""Issue #3012 (switch flows): tariff-switch confirm callbacks end in
tariff_id/period, not a subscription_id. The switch resolver must take the
subscription from FSM active_subscription_id (set by the switch entry), NEVER
from the trailing callback segment — otherwise, when that trailing number equals
one of the user's subscription ids, the WRONG subscription is switched/charged.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import app.database.crud.subscription as subcrud


def _patch_get_sub_by_id(monkeypatch):
    """get_subscription_by_id_for_user(db, sub_id, user_id) -> a sub with that id."""

    async def fake_get(db, sub_id, user_id):
        sub = MagicMock()
        sub.id = sub_id
        return sub

    monkeypatch.setattr(subcrud, 'get_subscription_by_id_for_user', fake_get)
