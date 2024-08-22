from functools import wraps, partial
from multiprocessing.connection import Connection
import select
from typing import ParamSpec, TypeVar, Union, Generic, Type, List
import multiprocessing as mp
import multiprocessing.shared_memory as smem
import pickle
import typing
import zmq
import zmq.asyncio
import asyncio
import signal
import inspect
import os
import sys
import logging
import time

from .asinc import make_async
from .logger import get_logger

T = TypeVar("T")
_pickler = pickle
logger = get_logger(logging.INFO)


def shorten_large_obj(obj, max_len=100):
    if __debug__:
        sz = sys.getsizeof(obj)
        if sz > max_len:
            return f"<{sz} bytes object>"
        if isinstance(obj, bytes):
            return _pickler.loads(obj)
        return obj
    return ""


class ProtoBase:
    def establish(self):
        return self

    def connect(self):
        return self

    def close(self):
        pass

    async def recv(self) -> bytes:
        raise NotImplementedError

    async def recv_multipart(self) -> bytes:
        raise NotImplementedError

    async def send(self, message: bytes):
        raise NotImplementedError

    async def send_multipart(self, message: bytes):
        raise NotImplementedError


class ZmqProto(ProtoBase):
    def __init__(self, port=5555, host="tcp://127.0.0.1"):
        self.port = port
        self.host = host
        self.server_address = f"{host}:{port}"
        self.context: zmq.asyncio.Context = None
        self.socket: zmq.asyncio.Socket = None

    def establish(self):
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.ROUTER)
        self.socket.bind(self.server_address)
        logger.info(f"Server established on {self.server_address}")
        return self

    def connect(self):
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.connect(self.server_address)
        return self

    def close(self):
        self.socket.close()
        self.context.destroy()

    async def recv(self):
        message = await self.socket.recv()
        logger.debug(f"  Got message '{shorten_large_obj(message)}'")
        return message

    async def recv_multipart(self):
        identity, message = await self.socket.recv_multipart()
        logger.debug(f"  Got message '{shorten_large_obj(message)}' from {identity.hex()}")
        return identity, message

    async def send(self, message):
        await self.socket.send(message)

    async def send_multipart(self, message):
        await self.socket.send_multipart(message)


class MpQueueProto(ProtoBase):
    def __init__(self):
        self.queue = mp.Queue()

    async def recv(self):
        message = self.queue.get()
        return message

    async def recv_multipart(self):
        message = self.queue.get()
        return None, message

    async def send(self, message):
        self.queue.put(message)

    async def send_multipart(self, message):
        await self.send(message[1])


class PipeProto(ProtoBase):
    def __init__(self):
        self.server_get, self.server_put = mp.get_context("spawn").Pipe()
        self.client_get, self.client_put = mp.get_context("spawn").Pipe()
        self.server = self.RealPipe(self.server_get, self.client_put)
        self.client = self.RealPipe(self.client_get, self.server_put)

    def establish(self, *args, **kwargs):
        return self.server

    def connect(self, *args, **kwargs):
        return self.client

    class RealPipe(ProtoBase):
        def __init__(self, in_pipe: Connection, out_pipe: Connection):
            self.in_pipe = in_pipe
            self.out_pipe = out_pipe

        async def recv(self):
            message = self.out_pipe.recv_bytes()
            logger.debug(f"  Got message '{shorten_large_obj(message)}'")
            return message

        async def recv_multipart(self):
            message = await self.recv()
            return None, message

        async def send(self, message):
            logger.debug(f"  Send message '{shorten_large_obj(message)}'")
            self.in_pipe.send_bytes(message)

        async def send_multipart(self, message):
            await self.send(message[1])


class SharedMemProto(ProtoBase):
    def __init__(self, size_per_slot=10 * 1024 * 1024, num_slots=10):
        self.size_per_slot = size_per_slot
        self.num_slots = num_slots
        self.server_queue = mp.Queue()
        self.client_queue = mp.Queue()
        self.server_slots = [
            smem.SharedMemory(f"liz.rpc_server_slot_{i}", True, size_per_slot) for i in range(num_slots)
        ]
        self.client_slots = [
            smem.SharedMemory(f"liz.rpc_client_slot_{i}", True, size_per_slot) for i in range(num_slots)
        ]

        # Warm up
        for i in range(5):
            for slot in self.server_slots:
                slot.buf[:] = b"\x00" * self.size_per_slot
                x = bytes(slot.buf[:])
                assert x == b"\x00" * self.size_per_slot
            for slot in self.client_slots:
                slot.buf[:] = b"\x00" * self.size_per_slot
                x = bytes(slot.buf[:])
                assert x == b"\x00" * self.size_per_slot

    def __del__(self):
        for i in range(self.num_slots):
            self.server_slots[i].close()
            self.server_slots[i].unlink()
            self.client_slots[i].close()
            self.client_slots[i].unlink()

    def establish(self):
        return self.RealSharedMem(self.client_slots, self.server_slots, self.client_queue, self.server_queue)

    def connect(self):
        return self.RealSharedMem(self.server_slots, self.client_slots, self.server_queue, self.client_queue)

    class RealSharedMem(ProtoBase):

        FLAG_SZ = 4
        NO_MESSAGE = int.to_bytes(0, FLAG_SZ)
        HAS_MESSAGE = int.to_bytes(2**30 + 1, FLAG_SZ)

        def __init__(
            self,
            read_shm: List[smem.SharedMemory],
            write_shm: List[smem.SharedMemory],
            read_offsets: mp.Queue,
            write_offsets: mp.Queue,
        ):
            """First byte of the memory marks if there is unread message"""
            self.read_slots = read_shm
            self.write_slots = write_shm
            self.read_offsets = read_offsets
            self.write_offsets = write_offsets
            self.get_read_offset_async = make_async(self.read_offsets.get)
            if len(read_shm) != len(write_shm):
                raise ValueError("Number of read and write slots must match.")
            self.num_slots = len(read_shm)
            self.size_per_slot = read_shm[0].size
            for i in range(self.num_slots):
                if (read_shm[i].size != self.size_per_slot) or (write_shm[i].size != self.size_per_slot):
                    raise ValueError("Shared memory slot sizes should be same.")
            self.read_counter = 0
            self.write_counter = 0

        def __del__(self):
            for i in range(self.num_slots):
                self.read_slots[i].close()
                self.write_slots[i].close()

        async def recv(self):
            self.read_counter //= self.num_slots
            slot = self.read_slots[self.read_counter]
            self.read_counter += 1

            offset = await self.get_read_offset_async()
            message = bytes(slot.buf[self.FLAG_SZ : offset + self.FLAG_SZ])
            slot.buf[:self.FLAG_SZ] = self.NO_MESSAGE
            return message

        async def recv_multipart(self):
            message = await self.recv()
            return None, message

        async def send(self, message):
            self.write_counter //= self.num_slots
            slot = self.write_slots[self.write_counter]
            self.write_counter += 1

            msg_sz = len(message)
            if msg_sz > self.size_per_slot:
                raise ValueError(f"Message size {msg_sz} bytes exceeds shared memory capacity {self.size_per_slot}.")

            if bytes(slot.buf[: self.FLAG_SZ]) != self.NO_MESSAGE:
                print(self.NO_MESSAGE, bytes(slot.buf[: self.FLAG_SZ]))
                raise ValueError(f"Running out of shared memory slots {slot.buf[:self.FLAG_SZ]}.")

            slot.buf[:self.FLAG_SZ] = self.HAS_MESSAGE
            slot.buf[self.FLAG_SZ : msg_sz + self.FLAG_SZ] = message
            self.write_offsets.put(msg_sz)

        async def send_multipart(self, message):
            await self.send(message[1])


class RPCServer:
    def __init__(self, cls_or_obj: Union[type, object], proto: ProtoBase):
        if isinstance(cls_or_obj, type):
            self.target_cls = cls_or_obj
            self.instance = None
        else:
            self.target_cls = cls_or_obj.__class__
            self.instance = cls_or_obj
        self.proto = proto
        self.loop: asyncio.AbstractEventLoop = None
        self.server_task: asyncio.Task = None
        self._func_dct = {}
        self._init_func_dct()

    def bind(self, instance):
        self.instance = instance

    def __call__(self, instance):
        self.instance = instance
        return self

    async def server_loop(self):
        if self.instance is None:
            raise ValueError("RPC server instance is not set")
        while True:
            logger.debug("Waiting...")
            try:
                identity, message = await self.proto.recv_multipart()
                result = await self.handle_request(identity, message)
                logger.debug(f"  Function result {result}")
                await self.proto.send_multipart([identity, _pickler.dumps(result)])
            except Exception as e:
                logger.debug(f"  Catch exception {e}")
                await self.proto.send_multipart([identity, _pickler.dumps(e)])

    async def handle_request(self, identity, message):
        method_name, args, kwargs = _pickler.loads(message)
        method = self._func_dct.get(method_name)
        result = await method(self.instance, *args, **kwargs)
        return result

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.server_task = self.loop.create_task(self.server_loop())

        def signal_handler() -> None:
            self.server_task.cancel()

        self.loop.add_signal_handler(signal.SIGINT, signal_handler)
        self.loop.add_signal_handler(signal.SIGTERM, signal_handler)

        try:
            await self.server_task
        except asyncio.CancelledError:
            print("Server task was cancelled.")
        finally:
            self.loop.remove_signal_handler(signal.SIGINT)
            self.loop.remove_signal_handler(signal.SIGTERM)
            self.proto.close()

    def _init_func_dct(self):
        for name, method in self.target_cls.__dict__.items():
            if callable(method) and not name.startswith("_"):
                if inspect.iscoroutinefunction(method):
                    self._func_dct[name] = method
                else:
                    self._func_dct[name] = make_async(method)


def RPCClient(cls: Type[T], proto: ProtoBase) -> T:
    class RPCClientProxy:
        def __init__(self, target_cls: Type[T], proto: ProtoBase):
            self.target_cls = target_cls
            self.proto = proto
            self._init_func_dct()

        def _init_func_dct(self):
            for name, value in self.target_cls.__dict__.items():
                if callable(value) and not name.startswith("_"):
                    proxy_method = self._make_rpc_wrapper(name, value)
                    proxy_method.__name__ = name
                    proxy_method.__signature__ = inspect.signature(value)
                    setattr(self.__class__, name, proxy_method)

        async def call_rpc(self, name, *args, **kwargs):
            await self.proto.send(_pickler.dumps((name, args, kwargs)))
            result = _pickler.loads(await self.proto.recv())
            if isinstance(result, Exception):
                raise result
            return result

        def _make_rpc_wrapper(self, name, method):
            @wraps(method)
            async def rpc_method(self, *args, **kwargs):
                return await self.call_rpc(name, *args, **kwargs)

            rpc_method.__signature__ = inspect.signature(method)
            rpc_method.__name__ = name
            return rpc_method

    return RPCClientProxy(cls, proto)
