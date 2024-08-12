import time
from globaler.enabler import DebugOnly, Enabled
from functools import wraps

def dec(func):
    setattr(func, "_override_enabler", True)
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

# Example usage
class A(DebugOnly):
    @DebugOnly.bypass
    def method(self, a):
        print(a)
        return len(a) * 3.14159
    
    @dec
    def m2(self):
        pass


a = A()
b = A()

a.method("Hello")

a.enabled = False
a.method("Hello 2")

b.method("Hello 3")

# start_time = time.time()
# for _ in range(1000000):
#     a.method("Hello world")
# duration = time.time() - start_time
# print(duration)