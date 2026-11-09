from math import ceil
from typing import TypeVar


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
