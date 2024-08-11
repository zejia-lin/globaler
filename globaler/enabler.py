import types
from functools import wraps


def debug_only(func):
    """Decorator that disables the function if __debug__ is False (when Python is run with -O)."""
    if __debug__:
        return func
    else:
        def no_op(*args, **kwargs):
            pass
        return no_op


def enabler(method):
    """Decorator that runs the method only if the object's "enabled" attribute is True."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if self.enabled:
            return method(self, *args, **kwargs)
        # No-op if not enabled
        return None
    return wrapper


class _EnablerMetaClass(type):
    def __new__(cls, name, bases, dct):
        cls.enabled = True
        cls.debug_only = True
        for attr_name, attr_value in dct.items():
            if isinstance(attr_value, types.FunctionType) and not (
                attr_name.startswith("__") and attr_name.endswith("__")
            ):
                dct[attr_name] = enabler(attr_value)
                if cls.debug_only:
                    dct[attr_name] = debug_only(dct[attr_name])
        return super().__new__(cls, name, bases, dct)


class EnableForDebug(metaclass=_EnablerMetaClass):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.enabled = True
        cls.debug_only = True