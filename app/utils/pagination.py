from math import ceil
from typing import Any, TypeVar

from aiogram.types import InlineKeyboardButton


T = TypeVar('T')


class PaginationResult[T]:
    def __init__(self, items: list[T], total_count: int, page: int, per_page: int):
        self.items = items
        self.total_count = total_count
        self.page = page
        self.per_page = per_page
        self.total_pages = ceil(total_count / per_page) if per_page > 0 else 1
        self.has_prev = page > 1
        self.has_next = page < self.total_pages
        self.prev_page = page - 1 if self.has_prev else None
        self.next_page = page + 1 if self.has_next else None


def paginate_list[T](items: list[T], page: int = 1, per_page: int = 10) -> PaginationResult[T]:
    total_count = len(items)

    start_index = (page - 1) * per_page
    end_index = start_index + per_page

    page_items = items[start_index:end_index]

    return PaginationResult(items=page_items, total_count=total_count, page=page, per_page=per_page)


def build_page_nav_row(
    current_page: int,
    total_pages: int,
    page_callback_prefix: str,
    *,
    texts: Any = None,
    current_callback: str = 'current_page',
) -> list[InlineKeyboardButton]:
    """Ряд листания «⬅️ N/M ➡️».

    callback_data соседних страниц — ``page_callback_prefix`` + номер страницы.
    Стрелки берутся из PAGINATION_PREV/PAGINATION_NEXT, если передан ``texts``,
    иначе — те же «⬅️»/«➡️» без локализации (как было в админских экранах).
    """
    prev_text = texts.t('PAGINATION_PREV', '⬅️') if texts is not None else '⬅️'
    next_text = texts.t('PAGINATION_NEXT', '➡️') if texts is not None else '➡️'

    row: list[InlineKeyboardButton] = []
    if current_page > 1:
        row.append(InlineKeyboardButton(text=prev_text, callback_data=f'{page_callback_prefix}{current_page - 1}'))
    row.append(InlineKeyboardButton(text=f'{current_page}/{total_pages}', callback_data=current_callback))
    if current_page < total_pages:
        row.append(InlineKeyboardButton(text=next_text, callback_data=f'{page_callback_prefix}{current_page + 1}'))
    return row
