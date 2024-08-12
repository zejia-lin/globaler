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


class _EnablerMetaClass(type):
    @staticmethod
    def _enabler(method):
        """Decorator that runs the method only if the object's "enabled" attribute is True."""
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            if self.enabled:
                return method(self, *args, **kwargs)
            # No-op if not enabled
            return None
        return wrapper
    
    @staticmethod
    def _override(func, keyword):
        setattr(func, keyword, True)
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

    def __new__(cls, name, bases, dct):
        # Checking base class for Enabled and DebugOnly
        if len(bases) > 0:
            for c in bases:
                if issubclass(c, (DebugOnly, Enabled)):
                    cls.enabled = c.enabled
                    cls.debug_only = c.debug_only
                    break
        else:
            cls.enabled = dct.get("enabled")
            cls.debug_only = dct.get("debug_only")

        # Decorating all methods with enabler and debug_only
        for attr_name, attr_value in dct.items():
            if isinstance(attr_value, types.FunctionType) and not (
                attr_name.startswith("__") and attr_name.endswith("__")
            ):
                if not hasattr(attr_value, "_override_enabled"):
                    dct[attr_name] = _EnablerMetaClass._enabler(attr_value)
                if cls.debug_only and not hasattr(attr_value, "_override_debug_only"):
                    dct[attr_name] = debug_only(dct[attr_name])
        return super().__new__(cls, name, bases, dct)


class DebugOnly(metaclass=_EnablerMetaClass):
    enabled = True
    debug_only = True
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.enabled = True
        cls.debug_only = True
    
    @staticmethod
    def bypass(func):
        return _EnablerMetaClass._override(func, "_override_debug_only")

class Enabled(metaclass=_EnablerMetaClass):
    enabled = True
    debug_only = False
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.enabled = True
        cls.debug_only = False

    @staticmethod
    def bypass(func):
        return _EnablerMetaClass._override(func, "_override_enabled")
