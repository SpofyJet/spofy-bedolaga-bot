"""main.py лежит вне пакета app, поэтому обход пакета его импорты не проверяет."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _exists(module: str) -> bool:
    path = ROOT / module.replace('.', '/')
    return path.with_suffix('.py').exists() or path.is_dir()


def test_main_imports_only_existing_app_modules() -> None:
    tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('app')
    }
    assert modules
    missing = sorted(module for module in modules if not _exists(module))
    assert not missing, missing
