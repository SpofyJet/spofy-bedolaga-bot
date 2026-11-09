"""Every `settings.X` in the code must exist, or the bot fails at the line that reads it.

Imports do not catch this: an attribute is resolved only when the line runs, and
startup code in main.py has no unit tests of its own.
"""

import ast
from pathlib import Path

from app.config import Settings
from app.database.models import PaymentMethod


ROOTS = ('app', 'main.py', 'scripts', 'migrations')


def _sources() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        path = Path(root)
        files.extend([path] if path.is_file() else sorted(path.rglob('*.py')))
    return files


def _missing(owner: str, known: set[str]) -> list[str]:
    missing = []
    for source in _sources():
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == owner
                and node.attr not in known
                and not node.attr.startswith('_')
            ):
                missing.append(f'{source}:{node.lineno} {owner}.{node.attr}')
    return missing


def test_every_setting_used_in_code_exists() -> None:
    assert _missing('settings', set(dir(Settings)) | set(Settings.model_fields)) == []


def test_every_payment_method_used_in_code_exists() -> None:
    assert _missing('PaymentMethod', set(dir(PaymentMethod))) == []
