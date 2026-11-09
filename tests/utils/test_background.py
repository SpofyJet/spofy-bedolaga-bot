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
