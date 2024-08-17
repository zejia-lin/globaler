from functools import wraps, partial
from multiprocessing.connection import Connection
import select
from typing import ParamSpec, TypeVar, Union, Generic, Type
import multiprocessing as mp
import multiprocessing.shared_memory as shm
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
from multiprocessing import shared_memory as smem

smem.SharedMemory


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
        logger.debug(
            f"  Got message '{shorten_large_obj(message)}' from {identity.hex()}"
        )
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
    def __init__(self, queue_factory=mp.Queue, capacity=10 * 1024 * 1024):
        self.capacity = capacity
        self.server_write = shm.SharedMemory("liz.rpc_server_write", True, capacity)
        self.client_write = shm.SharedMemory("liz.rpc_client_write", True, capacity)
        self.server_queue = queue_factory()
        self.client_queue = queue_factory()
        for i in range(5):
            self.server_write.buf[:] = b"\x00" * self.capacity
            x = bytes(self.server_write.buf[:])
            self.client_write.buf[:] = b"\x00" * self.capacity
            x = bytes(self.server_write.buf[:])

    def __del__(self):
        self.server_write.close()
        self.server_write.unlink()
        self.client_write.close()
        self.client_write.unlink()

    def establish(self, *args, **kwargs):
        return self.RealSharedMem(
            self.client_write, self.server_write, self.client_queue, self.server_queue
        )

    def connect(self, *args, **kwargs):
        return self.RealSharedMem(
            self.server_write, self.client_write, self.server_queue, self.client_queue
        )

    class RealSharedMem(ProtoBase):

        def __init__(
            self,
            read_shm: smem.SharedMemory,
            write_shm: smem.SharedMemory,
            read_offset,
            write_offset,
        ):
            self.read_shm = read_shm
            self.write_shm = write_shm
            self.read_offset = read_offset
            self.write_offset = write_offset

        def __del__(self):
            self.read_shm.close()
            self.write_shm.close()

        async def recv(self):
            offset = self.read_offset.get()
            message = bytes(self.read_shm.buf[:offset])
            return message

        async def recv_multipart(self):
            message = await self.recv()
            return None, message

        async def send(self, message):
            msg_sz = len(message)
            if msg_sz > self.write_shm.size:
                raise ValueError("Message size exceeds shared memory capacity.")

            self.write_shm.buf[:msg_sz] = message
            self.write_offset.put(msg_sz)

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
