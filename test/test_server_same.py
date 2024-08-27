import os
import pickle
import sys
import asyncio
import time
import multiprocessing as mp

from globaler import RPCClient, RPCServer, ZmqProto

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


def serve(proto_factory):
    proto = proto_factory.establish()
    server = RPCServer(MyClass(), proto)
    asyncio.run(server.run())


def client(proto_factory):
    repeat = 10
    proto = proto_factory.connect()
    cc = RPCClient(MyClass, proto)
    print(f"Local pid {os.getpid()}")
    print(f"Remote pid {asyncio.run(cc.getpid())}")
    print(f"Remote pid sync {asyncio.run(cc.getpid_sync())}")
    print(f"Remote add {asyncio.run(cc.add(1, 2))}")
    print(f"Remote add sync {asyncio.run(cc.add_sync(1, 2))}")

    large_data = "xxx" * 10**3
    print("dta len", len(large_data))
    for i in range(10):
        response = asyncio.run(cc.send_large_data(large_data))

    start_time = time.time()
    for i in range(repeat):
        response = asyncio.run(cc.send_large_data(large_data))
    end_time = time.time()

    print(f"Send and receive {sys.getsizeof(pickle.dumps(large_data)) / 1e6} MB of data: {(end_time - start_time) / repeat} seconds")
    print(f"Response: {response}")


def same_proc():
    proto = ZmqProto()
    mp.Process(target=serve, args=(proto,)).start()
    time.sleep(1)
    mp.Process(target=client, args=(proto,)).start()
    exit(0)


if __name__ == "__main__":
    same_proc()
