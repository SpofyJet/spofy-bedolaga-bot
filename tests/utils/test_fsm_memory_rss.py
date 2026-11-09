import builtins
import io
import resource

from app.utils import fsm_memory


def _fake_statm(monkeypatch, pages: int) -> None:
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == '/proc/self/statm':
            return io.StringIO(f'100000 {pages} 300 1 0 5000 0\n')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', fake_open)


def test_current_rss_is_read_from_statm_not_from_peak(monkeypatch) -> None:
    pages = 200 * 1024 * 1024 // resource.getpagesize()
    _fake_statm(monkeypatch, pages)
    monkeypatch.setattr(fsm_memory, 'peak_rss_mb', lambda: 900.0)

    assert fsm_memory.current_rss_mb() == 200.0


def test_falls_back_to_peak_without_proc(monkeypatch) -> None:
    def no_proc(path, *args, **kwargs):
        raise FileNotFoundError(path)

    monkeypatch.setattr(builtins, 'open', no_proc)
    monkeypatch.setattr(fsm_memory, 'peak_rss_mb', lambda: 321.0)

    assert fsm_memory.current_rss_mb() == 321.0


def test_log_line_has_current_and_peak(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(fsm_memory, 'current_rss_mb', lambda: 200.0)
    monkeypatch.setattr(fsm_memory, 'peak_rss_mb', lambda: 900.0)
    monkeypatch.setattr(fsm_memory.logger, 'info', lambda event, **kw: calls.append((event, kw)))

    fsm_memory.log_memory('startup')

    assert calls == [('startup: RSS', {'rss_mb': 200.0, 'peak_mb': 900.0})]
