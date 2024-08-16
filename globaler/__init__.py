from .timer import Timer
from .enabler import DebugOnly, Enabled, debug_only
from . import asinc
from . import rpc
from .rpc import RPCClient, RPCServer, ZmqProto

__version__ = "0.1.0"

__all__ = [
    "Timer",
    "getTimer",
    "getGlobal",
    "DebugOnly",
    "Enabled",
    "debug_only",
]

_global_dict = {}

def getGlobal():
    return _global_dict

_global_timer = Timer()

def getTimer():
    return _global_timer
