"""Баннер по состоянию человека: нужный файл, общий баннер при любой неполадке, кэш file_id на вариант."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.middlewares.banner_variant import banner_variant_for
from app.utils import message_patch


def _sub(active=True, trial=False):
    return SimpleNamespace(is_active=active, is_trial=trial)


def test_variant_for_each_state():
    assert banner_variant_for(SimpleNamespace(subscriptions=[], language='ru')) == 'new'
    assert banner_variant_for(SimpleNamespace(subscriptions=[_sub(trial=True)], language='ru')) == 'trial'
    assert banner_variant_for(SimpleNamespace(subscriptions=[_sub()], language='ru')) == 'paid'
    assert banner_variant_for(SimpleNamespace(subscriptions=[_sub(active=False)], language='ru')) == 'expired'


def test_paid_wins_over_trial_and_language_suffix():
    both = SimpleNamespace(subscriptions=[_sub(trial=True), _sub()], language='en')
    assert banner_variant_for(both) == 'paid_en'
    assert banner_variant_for(SimpleNamespace(subscriptions=[], language='en-US')) == 'new_en'


def test_unknown_user_or_broken_relation_means_generic_banner():
    assert banner_variant_for(None) is None

    class Broken:
        language = 'ru'

        @property
        def subscriptions(self):
            raise RuntimeError('связь не загружена')

    assert banner_variant_for(Broken()) is None


@pytest.fixture
def banners(tmp_path, monkeypatch):
    monkeypatch.setattr(message_patch, 'BANNERS_DIR', tmp_path)
    monkeypatch.setattr(message_patch, '_variant_file_ids', {})
    monkeypatch.setattr(message_patch, '_variant_valid', {})
    return tmp_path


def _png(path: Path):
    Image.new('RGB', (64, 26), (0, 8, 29)).save(path)


def test_variant_file_is_used_and_cached_by_file_id(banners):
    _png(banners / 'paid.png')
    token = message_patch.set_banner_variant('paid')
    try:
        media = message_patch.get_logo_media()
        assert Path(media.path) == banners / 'paid.png'
        message_patch._cache_logo_file_id(SimpleNamespace(photo=[SimpleNamespace(file_id='FILE-PAID')]))
        assert message_patch.get_logo_media() == 'FILE-PAID'
    finally:
        message_patch.reset_banner_variant(token)


def test_variants_do_not_share_file_ids(banners):
    _png(banners / 'paid.png')
    _png(banners / 'new.png')
    token = message_patch.set_banner_variant('paid')
    message_patch._cache_logo_file_id(SimpleNamespace(photo=[SimpleNamespace(file_id='FILE-PAID')]))
    message_patch.reset_banner_variant(token)
    token = message_patch.set_banner_variant('new')
    try:
        media = message_patch.get_logo_media()
        assert media != 'FILE-PAID'
        assert Path(media.path) == banners / 'new.png'
    finally:
        message_patch.reset_banner_variant(token)


def test_missing_or_broken_variant_falls_back_to_generic_banner(banners):
    (banners / 'expired.png').write_bytes(b'not an image')
    for variant in ('expired', 'trial'):  # битый файл и отсутствующий файл
        token = message_patch.set_banner_variant(variant)
        try:
            assert message_patch._variant_path() is None
        finally:
            message_patch.reset_banner_variant(token)


def test_replacing_the_file_drops_the_cached_file_id(banners):
    _png(banners / 'paid.png')
    token = message_patch.set_banner_variant('paid')
    try:
        message_patch.get_logo_media()
        message_patch._cache_logo_file_id(SimpleNamespace(photo=[SimpleNamespace(file_id='OLD')]))
        Image.new('RGB', (128, 52), (1, 2, 3)).save(banners / 'paid.png')  # оператор обновил картинку
        media = message_patch.get_logo_media()
        assert media != 'OLD'
    finally:
        message_patch.reset_banner_variant(token)


def test_shipped_banners_are_valid_and_fit_telegram_limits():
    root = Path(__file__).resolve().parent.parent / 'banners'
    names = {f'{state}{suffix}' for state in ('new', 'trial', 'paid', 'expired') for suffix in ('', '_en')}
    for name in names:
        path = root / f'{name}.png'
        assert path.is_file(), name
        with Image.open(path) as img:
            width, height = img.size
            assert (width, height) == (1280, 512), name
        assert path.stat().st_size < 400_000, name
