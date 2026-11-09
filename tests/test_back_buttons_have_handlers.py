"""Кнопка «Назад» на экранах покупки должна вести на зарегистрированный обработчик."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = ('app/handlers/simple_subscription.py', 'app/handlers/subscription/purchase.py')


def _callback_values(source: str) -> set[str]:
    values = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == 'callback_data' and isinstance(node.value, ast.Constant):
            values.add(node.value.value)
    return values


def test_no_button_points_to_missing_subscription_callback() -> None:
    for name in FILES:
        assert 'subscription' not in _callback_values((ROOT / name).read_text(encoding='utf-8')), name


def test_menu_subscription_handler_is_registered() -> None:
    purchase = (ROOT / 'app/handlers/subscription/purchase.py').read_text(encoding='utf-8')
    assert "F.data == 'menu_subscription'" in purchase
