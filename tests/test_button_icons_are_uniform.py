"""Один значок на одно действие: «⬅️» для возврата, «❌ Отмена», «🛟 Поддержка»."""

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
STRAY = re.compile(r'◀️ |✖️ (Отмена|Cancel)|🛠️ (Поддержка|Support)')


@pytest.mark.parametrize('language', ['ru', 'en'])
def test_locale_has_no_stray_icons(language: str) -> None:
    values = json.loads((ROOT / f'app/localization/locales/{language}.json').read_text(encoding='utf-8'))
    assert {key: text for key, text in values.items() if isinstance(text, str) and STRAY.search(text)} == {}


def test_code_defaults_have_no_stray_icons() -> None:
    found = [
        str(path.relative_to(ROOT))
        for path in (ROOT / 'app').rglob('*.py')
        if STRAY.search(path.read_text(encoding='utf-8'))
    ]
    assert found == []
