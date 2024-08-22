import os
import sys
import asyncio
import time

from globaler import RPCClient, RPCServer, ZmqProto
from globaler.rpc import SharedMemProto


class MyClass:
    async def getpid(self):
        return f"hello from {os.getpid()}"

    def getpid_sync(self):
        return f"sync hello from {os.getpid()}"

    async def add(self, a, b):
        return a + b

    def add_sync(self, a, b):
        return a + b

    def send_large_data(self, data):
        return f"Received {len(data)} bytes of data"


async def serve():
    proto = SharedMemProto(create=True, size_per_slot=1024*1024)
    proto.establish(5555)
    server = RPCServer(MyClass(), proto)
    task = asyncio.create_task(server.run())
    print("Non-blocking server started")
    await task


async def client():
    repeat = 10
    proto = SharedMemProto(create=False, size_per_slot=1024*1024)
    proto.connect(5555)
    cc = RPCClient(MyClass, proto)
    print(f"Local pid {os.getpid()}")
    print(f"Remote pid {await cc.getpid()}")
    print(f"Remote pid sync {await cc.getpid_sync()}")
    print(f"Remote add {await cc.add(1, 2)}")
    print(f"Remote add sync {await cc.add_sync(1, 2)}")

    large_data = "x" * 10**6  # 1 MB of data
    for i in range(10):
        response = await cc.send_large_data(large_data)

    start_time = time.time()
    for i in range(repeat):
        response = await cc.send_large_data(large_data)
    end_time = time.time()

    print(f"Send and receive 1 MB of data: {(end_time - start_time) / repeat} seconds")
    print(f"Response: {response}")



if __name__ == "__main__":
    method = sys.argv[1]
    if method == "serve":
        asyncio.run(serve())
    else:
        asyncio.run(client())
