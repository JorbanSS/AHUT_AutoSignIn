import asyncio
import inspect
import threading
from typing import Any, Optional


class AsyncLoopRunner:
    def __init__(self):
        self._ready = threading.Event()
        self._closed = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        if self._loop is None:
            raise RuntimeError("failed to initialize async event loop thread")

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()

        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    def run(self, awaitable_obj: Any) -> Any:
        if not inspect.isawaitable(awaitable_obj):
            return awaitable_obj
        if self._closed or self._loop is None:
            raise RuntimeError("async loop runner is closed")

        future = asyncio.run_coroutine_threadsafe(awaitable_obj, self._loop)
        return future.result()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
