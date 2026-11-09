import pytest

from app.external.remnawave_api import RemnaWaveAPI


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('http://remnawave:3000', 'local'),
        ('https://localhost:3000', 'local'),
        ('https://127.0.0.1', 'local'),
        ('https://10.0.0.5', 'local'),
        ('https://172.16.0.5', 'local'),
        ('https://192.168.1.2', 'local'),
        ('https://panel.local', 'local'),
        ('https://10.evil.example', 'external'),
        ('https://172.evil.example', 'external'),
        ('https://192.168.evil.example', 'external'),
        ('https://172.64.0.1', 'external'),
        ('https://panel.example.com', 'external'),
    ],
)
def test_detect_connection_type(url: str, expected: str) -> None:
    api = RemnaWaveAPI(base_url=url, api_key='key')
    assert api._detect_connection_type() == expected
