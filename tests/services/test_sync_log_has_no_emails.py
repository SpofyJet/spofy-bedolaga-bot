"""Суточная синхронизация не пишет адреса почты в лог уровня INFO и выше."""

import ast
from pathlib import Path


def test_email_goes_to_debug_only() -> None:
    path = Path(__file__).resolve().parents[2] / 'app/services/remnawave_service.py'
    loud = []
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {'info', 'warning', 'error', 'exception'}
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == 'logger'
            and any(kw.arg in {'panel_email', 'email'} for kw in node.keywords)
        ):
            loud.append(node.lineno)
    assert loud == []
