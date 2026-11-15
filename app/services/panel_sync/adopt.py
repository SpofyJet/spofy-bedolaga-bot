"""Создание аккаунта в панели без дубля: сначала опознать по shortUuid.

Вынесено из грейс-доступа при его удалении (15.11.2026): через эту функцию шли
все админские создания аккаунта, и защита от второго панельного аккаунта нужна
и без грейса.
"""

from __future__ import annotations

from typing import Any


def create_payload_as_patch(create_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Превратить payload создания в безопасный payload обновления.

    Две ловушки, из-за которых нельзя просто переслать create-тело в PATCH:

    * ``username`` — в 3.0.0 это альтернативный идентификатор записи, а команда
      требует ровно один; вместе с ``id`` он лишний.
    * ``active_internal_squads`` — ``create_user`` пропускает пустой список
      (``if active_internal_squads:``), а ``update_user`` — только ``None``
      (``if ... is not None``). В контракте поле опционально: не прислать =
      «не трогать», прислать ``[]`` = «снять все сквады». Переслав пустой
      список, мы бы сняли у живого оплаченного аккаунта все инбаунды — он
      остался бы ACTIVE, но ссылка на подписку отдавала бы ноль конфигов.
      Ровно поэтому все остальные update-ветки в проекте гейтят это поле
      через ``if subscription.connected_squads:``.
    """
    patch = {key: value for key, value in create_kwargs.items() if key != 'username'}
    if not patch.get('active_internal_squads'):
        patch.pop('active_internal_squads', None)
    return patch


async def adopt_or_create_panel_user(api: Any, adopt_short_uuid: str | None, **create_kwargs: Any) -> Any:
    """Опознать существующего панельного пользователя по shortUuid, иначе создать.

    У строки, привязанной до апгрейда на Remnawave 3.0.0, числового id нет (его
    проставляет бэкфил), но shortUuid панель по-прежнему знает. Без этой проверки
    любое админское «создать/синхронизировать» заводит ВТОРОЙ панельный аккаунт,
    затирает shortUuid новым — и оплаченный оригинал становится ненаходимым.

    Проверка живёт здесь, потому что через этот хелпер проходят все админские
    пути создания; дублировать её по call-site значит однажды забыть.
    """
    short_uuid = (adopt_short_uuid or '').strip()
    if short_uuid:
        # Только 404 (→ None) доказывает, что аккаунта нет. Любая другая ошибка
        # пробрасывается: создать нового «на всякий случай» — это и есть дубль.
        adopted = await api.get_user_by_short_uuid(short_uuid)
        if adopted is not None:
            # Подхватить аккаунт мало — вызывающий просил ПРИВЕСТИ панель к
            # переданному состоянию и трактует результат как «панель теперь
            # такая». Без PATCH админское «продлить» отрапортовало бы успех,
            # оставив в панели старые статус/дату/лимиты, а у клиента —
            # нерабочий VPN. `username` в PATCH не идёт: это create-only поле,
            # переименовывать существующий аккаунт мы не собираемся.
            update_kwargs = create_payload_as_patch(create_kwargs)
            return await api.update_user(user_id=adopted.id, **update_kwargs)
    return await api.create_user(**create_kwargs)
