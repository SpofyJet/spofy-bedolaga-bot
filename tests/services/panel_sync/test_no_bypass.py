"""В панель пишет только сервис синхронизации.

Каждое расхождение, которое пришлось чинить — переписанная дата окончания,
снятая блокировка, стёртые инбаунды, одинаковые имена у двух тарифов, — появилось
одинаково: правило скопировали в соседний модуль, потом починили одну копию.
Сторож ловит следующую копию в момент появления, а не через полгода в отчёте.
"""

import ast
import pathlib

import pytest


#: Вызовы клиента панели, которыми бот меняет её состояние.
_PANEL_WRITE_CALLS = frozenset({'create_user', 'update_user'})

#: Кому можно звать их напрямую.
_ALLOWED = {
    # Сам сервис синхронизации — здесь правила и живут.
    'app/services/panel_sync/writer.py',
    # Клиент панели: это и есть обёртка над HTTP.
    'app/external/remnawave_api.py',
    # Усыновление уже существующего аккаунта панели: это create_call, который
    # админские пути передают в push_subscription, — payload собирает сервис.
    'app/services/panel_sync/adopt.py',
}


def _python_files() -> list[pathlib.Path]:
    return [path for path in sorted(pathlib.Path('app').rglob('*.py')) if str(path) not in _ALLOWED]


def _direct_panel_writes(path: pathlib.Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _PANEL_WRITE_CALLS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {'api', 'client'}
    ]


@pytest.mark.parametrize('path', _python_files(), ids=str)
def test_nobody_writes_to_the_panel_directly(path):
    lines = _direct_panel_writes(path)

    assert not lines, (
        f'{path}: запись в панель мимо app/services/panel_sync — строки {lines}. '
        f'Нужна подписка целиком — push_subscription; одно-два поля — only_fields; '
        f'карточка аккаунта — patch_panel_account; сквады тарифа — patch_panel_squads.'
    )
