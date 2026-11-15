"""Guard for the issue #3012 footgun in resolve_subscription_from_context.

The whole codebase relies on one safety property: the resolver only treats a
callback's TRAILING segment as a subscription_id when the callback is
COLON-separated (`prefix:sub_id`). Underscore-suffixed callbacks (`add_traffic_30`,
`change_devices_5`, `autopay_days_7`) must NOT have their trailing number used as a
subscription_id — they fall through to FSM `active_subscription_id`. If a future
change to the resolver breaks this (e.g. also splitting on `_`), every
underscore-callback handler would silently regress into the wrong-subscription bug.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import app.database.crud.subscription as subcrud


def _patch_get_sub_by_id(monkeypatch):
    async def fake_get(db, sub_id, user_id):
        sub = MagicMock()
        sub.id = sub_id
        return sub

    monkeypatch.setattr(subcrud, 'get_subscription_by_id_for_user', fake_get)
