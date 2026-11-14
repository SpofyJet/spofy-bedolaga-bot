"""Adversarial inputs must not stall parsing."""

import signal
from contextlib import contextmanager

import pytest

from app.services.server_status_service import ServerStatusService
from app.utils import rich_admin, validators


@contextmanager
def parsing_deadline():
    def expired(*_):
        raise TimeoutError('parsing exceeded two seconds')

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 2)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def test_unterminated_escaped_metric_label_is_bounded():
    with parsing_deadline():
        assert ServerStatusService()._parse_labels('A="' + '\\!' * 100) == {}


@pytest.mark.parametrize('validate', [validators.validate_html_tags, validators.validate_html_structure])
def test_unterminated_long_tag_is_bounded(validate):
    with parsing_deadline():
        validate('<A' + '-' * 100_000)


@pytest.mark.parametrize('tag', ['pre', 'blockquote'])
def test_unterminated_rich_blocks_are_bounded(tag):
    with parsing_deadline():
        assert rich_admin._inline_newlines_to_rich(f'<{tag}>' * 20_000)


def test_metric_label_escapes_and_adjacent_labels_still_parse():
    labels = ServerStatusService()._parse_labels(r'name="edge\"one",address="example.com",protocol="vless"')
    assert labels == {'name': 'edge"one', 'address': 'example.com', 'protocol': 'vless'}


def test_rich_segmentation_preserves_existing_short_input_semantics():
    import itertools
    import re

    tokens = ['text\n', '<pre>', '</pre>', '<blockquote>', '</blockquote>']
    for size in range(5):
        for pieces in itertools.product(tokens, repeat=size):
            text = ''.join(pieces)
            expected = re.split(r'(<blockquote>.*?</blockquote>|<pre>.*?</pre>)', text, flags=re.IGNORECASE | re.DOTALL)
            assert rich_admin._split_blocks(text, frozenset({'blockquote', 'pre'})) == expected


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (
            'https://github.com/owner/repo/blob/main/list.txt',
            'https://raw.githubusercontent.com/owner/repo/main/list.txt',
        ),
        (
            'https://github.com/owner/repo/blob/main/a/blob/list.txt?q=github.com',
            'https://raw.githubusercontent.com/owner/repo/main/a/blob/list.txt?q=github.com',
        ),
        ('https://github.com.example/list.txt', 'https://github.com.example/list.txt'),
        ('https://example.com/github.com/blob/list.txt', 'https://example.com/github.com/blob/list.txt'),
        ('https://example.com/?source=github.com', 'https://example.com/?source=github.com'),
        (
            'https://raw.githubusercontent.com/owner/repo/main/list.txt',
            'https://raw.githubusercontent.com/owner/repo/main/list.txt',
        ),
    ],
)
def test_blacklist_conversion_uses_parsed_host_and_blob_path(source, expected):
    from app.services.blacklist_service import _blacklist_raw_url

    assert _blacklist_raw_url(source) == expected
