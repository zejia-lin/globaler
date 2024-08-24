import asyncio
from functools import partial, wraps
from typing import Awaitable, Callable, TypeVar
import torch

T = TypeVar("T")


def make_async(func: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    """Take a blocking function, and run it on in an executor thread.

    This function prevents the blocking function from blocking the
    asyncio event loop.
    The code in this function needs to be thread safe.
    """
    def _async_wrapper(*args, **kwargs) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        p_func = partial(func, *args, **kwargs)
        return loop.run_in_executor(executor=None, func=p_func)
    return _async_wrapper


class async_inference_mode:
    def __enter__(self):
        self.ctx = torch.inference_mode()
        self.ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Exit the inference mode context
        self.ctx.__exit__(exc_type, exc_val, exc_tb)
        
    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with torch.inference_mode():
                return await func(*args, **kwargs)
        return wrapper
