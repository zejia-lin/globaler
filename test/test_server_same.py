import os
import pickle
import sys
import asyncio
import time
import multiprocessing as mp

from globaler import RPCClient, RPCServer, ZmqProto
from globaler.rpc import QueueProto

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


def serve(proto):
    server = RPCServer(MyClass(), proto)
    asyncio.run(server.run())


def client(proto):
    repeat = 10
    cc = RPCClient(MyClass, proto)
    print(f"Local pid {os.getpid()}")
    print(f"{os.getpid()}: Remote pid {asyncio.run(cc.getpid())}")
    print(f"{os.getpid()}: Remote pid sync {asyncio.run(cc.getpid_sync())}")
    print(f"{os.getpid()}: Remote add {asyncio.run(cc.add(1, 2))}")
    print(f"{os.getpid()}: Remote add sync {asyncio.run(cc.add_sync(1, 2))}")

    large_data = "xxx" * 10**3
    print("dta len", len(large_data))
    for i in range(10):
        response = asyncio.run(cc.send_large_data(large_data))

    start_time = time.time()
    for i in range(repeat):
        response = asyncio.run(cc.send_large_data(large_data))
    end_time = time.time()

    print(f"{os.getpid()}: Send and receive {sys.getsizeof(pickle.dumps(large_data)) / 1e6} MB of data: {(end_time - start_time) / repeat} seconds")
    print(f"{os.getpid()}: Response: {response}")
    print(f"{os.getpid()}: Finished")


def same_proc():
    ctx = mp.get_context("spawn")
    proto = QueueProto(ctx.SimpleQueue, 2)
    ctx.Process(target=serve, args=(proto.establish(),)).start()
    time.sleep(1)
    ctx.Process(target=client, args=(proto.connect(),)).start()
    ctx.Process(target=client, args=(proto.connect(),)).start()
    exit(0)


if __name__ == "__main__":
    same_proc()
