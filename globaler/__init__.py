from .timer import Timer

__version__ = "0.1.0"

__all__ = [
    "Timer",
    "getTimer",
    "getDict",
]

_global_dict = {}

def getDict():
    return _global_dict

_global_timer = Timer()

def getTimer():
    return _global_timer
