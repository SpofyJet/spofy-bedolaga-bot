import asyncio

from app.utils import background


async def test_spawn_keeps_reference_until_task_finishes() -> None:
    release = asyncio.Event()

    task = background.spawn_background_task(release.wait())
    assert task in background._running_tasks

    release.set()
    await task
    await asyncio.sleep(0)
    assert task not in background._running_tasks


async def test_failed_task_is_released_and_its_exception_consumed() -> None:
    async def fail() -> None:
        raise RuntimeError('boom')

    task = background.spawn_background_task(fail())
    await asyncio.wait({task})
    await asyncio.sleep(0)

    assert task not in background._running_tasks


async def test_spawn_passes_task_name() -> None:
    task = background.spawn_background_task(asyncio.sleep(0), name='mass-send-resume')
    assert task.get_name() == 'mass-send-resume'
    await task


def test_main_does_not_spawn_unreferenced_tasks() -> None:
    """Задачи запуска идут через spawn_background_task: иначе сборщик мусора может снять их на полпути."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(background.__file__).parents[2].joinpath('main.py').read_text(encoding='utf-8'))
    bare = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == 'create_task'
    ]
    assert bare == []
