"""/paysupport must answer everyone who paid: Telegram requires it of bots that sell for Stars
(Bot Developer Terms 6.2.1). The flag comes from the matched handler, never from message text.
"""

from typing import Any

from aiogram.types import Message


def is_payment_support_handler(event: Any, data: dict) -> bool:
    flags = getattr(data.get('handler'), 'flags', None)
    if not isinstance(flags, dict) or flags.get('public_payment_support') is not True:
        return False
    if not isinstance(event, Message) or event.chat.type != 'private':
        return False
    return bool(event.from_user) and not event.from_user.is_bot
