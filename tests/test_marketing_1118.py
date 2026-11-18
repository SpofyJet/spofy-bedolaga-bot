from types import SimpleNamespace

from app.config import settings
from app.handlers.referral import _build_referral_share_url, build_referral_share_text
from app.localization.texts import get_texts
from app.services import bypass_downgrade


def test_share_text_is_what_the_bot_share_link_carries():
    from urllib.parse import unquote

    texts = get_texts('ru')
    text = build_referral_share_text(texts)
    url = _build_referral_share_url('https://t.me/bot?start=ref', texts)
    assert unquote(url.split('&text=')[1]) == text
    assert '<tg-emoji' not in text
    assert 'комисси' not in text


def test_has_bypass(monkeypatch):
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', 'sq-bypass', raising=False)
    monkeypatch.setattr(bypass_downgrade, 'is_suspension_effective', lambda sub: getattr(sub, 'suspended', False))
    plain = SimpleNamespace(connected_squads=['sq-main'], traffic_limit_gb=0)
    unlimited = SimpleNamespace(connected_squads=['sq-main', 'sq-bypass'], traffic_limit_gb=0)
    suspended = SimpleNamespace(connected_squads=['sq-off'], traffic_limit_gb=50, suspended=True)
    assert bypass_downgrade.has_bypass(plain) is False
    assert bypass_downgrade.has_bypass(unlimited) is True
    assert bypass_downgrade.has_bypass(suspended) is True
    monkeypatch.setattr(settings, 'BYPASS_SQUAD_UUID', '', raising=False)
    assert bypass_downgrade.has_bypass(unlimited) is False
