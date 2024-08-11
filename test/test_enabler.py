import time
from globaler.enabler import EnableForDebug

# Example usage
class A(EnableForDebug):
    def method(self, a):
        return len(a) * 3.14159


a = A()
a.enabled = True
a.method("Hello")  # Prints "Hello" because enabled is True

a.enabled = True
a.method("Hello 2")  # Does nothing because enabled is False


start_time = time.time()
for _ in range(1000000):
    a.method("Hello world")
duration = time.time() - start_time
print(duration)