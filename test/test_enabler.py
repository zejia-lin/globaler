import time
from globaler.enabler import DebugOnly

# Example usage
class A(DebugOnly):
    def method(self, a):
        print(a)
        return len(a) * 3.14159


a = A()
b = A()
# a.enabled = False
a.method("Hello")  # Prints "Hello" because enabled is True

a.enabled = False
a.method("Hello 2")  # Does nothing because enabled is False
# b.enabled = True
b.method("Hello 3")
# print(A.enabled, a.enabled, b.enabled)

# start_time = time.time()
# for _ in range(1000000):
#     a.method("Hello world")
# duration = time.time() - start_time
# print(duration)