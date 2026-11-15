"""Общий ряд листания «⬅️ N/M ➡️» (app.utils.pagination.build_page_nav_row)."""

from app.localization.texts import get_texts
from app.utils.pagination import build_page_nav_row


def _row(row):
    return [(b.text, b.callback_data) for b in row]


def test_middle_page_has_both_arrows():
    row = build_page_nav_row(2, 3, 'devices_page_', texts=get_texts('ru'))
    assert _row(row) == [('⬅️', 'devices_page_1'), ('2/3', 'current_page'), ('➡️', 'devices_page_3')]


def test_first_and_last_page_drop_one_arrow():
    assert _row(build_page_nav_row(1, 3, 'p_')) == [('1/3', 'current_page'), ('➡️', 'p_2')]
    assert _row(build_page_nav_row(3, 3, 'p_')) == [('⬅️', 'p_2'), ('3/3', 'current_page')]


def test_custom_current_callback_and_prefix_with_ids():
    row = build_page_nav_row(2, 2, 'menu_faq_page:7:', current_callback='noop')
    assert _row(row) == [('⬅️', 'menu_faq_page:7:1'), ('2/2', 'noop')]


def test_arrows_come_from_texts_when_given():
    class _Texts:
        def t(self, key, default=None):
            return {'PAGINATION_PREV': '«', 'PAGINATION_NEXT': '»'}[key]

    row = build_page_nav_row(2, 3, 'x_', texts=_Texts())
    assert [b.text for b in row] == ['«', '2/3', '»']
    # Без texts — фиксированные стрелки, как было в админских списках.
    assert [b.text for b in build_page_nav_row(2, 3, 'x_')] == ['⬅️', '2/3', '➡️']
