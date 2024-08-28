import asyncio
import inspect
import io
import logging
import multiprocessing as mp
import os
import pickle
import signal
import traceback
from functools import wraps
from multiprocessing.connection import Connection
from multiprocessing.reduction import ForkingPickler
from typing import List, Type, TypeVar, Union

import zmq
import zmq.asyncio
from torch.multiprocessing.reductions import init_reductions

from .asinc import make_async
from .logger import get_logger

T = TypeVar("T")
logger = get_logger(logging.INFO)

# Init pytorch reductions
init_reductions()


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

    async def send(self, message):
        raise NotImplementedError

    async def send_multipart(self, message):
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
        logger.info(f"ZMQ server established on {self.server_address}")
        return self

    def connect(self):
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.connect(self.server_address)
        logger.info(f"ZMQ client connected to {self.server_address}")
        return self

    def close(self):
        self.socket.close()
        self.context.destroy()

    async def recv(self):
        message = pickle.loads(await self.socket.recv())
        logger.debug(f"Get {message}")
        return message

    async def recv_multipart(self):
        identity, buf = await self.socket.recv_multipart()
        message = pickle.loads(buf)
        logger.debug(f"Get multipart {identity} {message}")
        return identity, message

    async def send(self, message):
        buf = io.BytesIO()
        ForkingPickler(buf, pickle.HIGHEST_PROTOCOL).dump(message)
        logger.debug(f"Sending {message}, {buf.getvalue()}")
        await self.socket.send(buf.getvalue())

    async def send_multipart(self, message):
        buf = io.BytesIO()
        ForkingPickler(buf, pickle.HIGHEST_PROTOCOL).dump(message[1])
        logger.debug(f"Sending multipart {message}")
        await self.socket.send_multipart([message[0], buf.getvalue()])


class QueueProto(ProtoBase):
    def __init__(self, queue_factory: Type[mp.SimpleQueue], max_clients=1):
        self.server_queue = queue_factory()
        self.max_clients = max_clients
        self.client_queues: List[mp.SimpleQueue] = []
        self.clients: List["QueueProto.ClientQueue"] = []
        self.availabel_clients = set(range(max_clients))
        for identity in range(max_clients):
            self.client_queues.append(queue_factory())
            self.clients.append(self.ClientQueue(identity, self.client_queues[identity], self.server_queue, self))
        self.server = self.ServerQueue(self.server_queue, self.client_queues)

    def establish(self):
        return self.server

    def connect(self):
        if len(self.availabel_clients) == 0:
            raise RuntimeError("No available clients")
        identity = self.availabel_clients.pop()
        return self.clients[identity]

    def disconnect(self, identity):
        self.availabel_clients.add(identity)

    class ServerQueue:
        def __init__(self, read: mp.SimpleQueue, writes: List[mp.SimpleQueue]):
            self.read = read
            self.writes = writes

        async def recv(self):
            raise NotImplementedError("Server does not support recv")

        async def recv_multipart(self):
            identity, message = self.read.get()
            logger.debug(f"Get {message} from {identity}")
            return identity, message

        async def send(self, message):
            raise NotImplementedError("Server does not support send")

        async def send_multipart(self, message):
            identity, message = message
            logger.debug(f"Sending {message} to {identity}")
            self.writes[identity].put(message)

    class ClientQueue:
        def __init__(self, identity, read: mp.SimpleQueue, write: mp.SimpleQueue, that):
            self.identity = identity
            self.read = read
            self.write = write
            self.that = that

        async def recv(self):
            message = self.read.get()
            logger.debug(f"Get {message}")
            return message

        async def recv_multipart(self):
            raise NotImplementedError("Client does not support multipart message")

        async def send(self, message):
            logger.debug(f"Sending {message}")
            self.write.put((self.identity, message))

        async def send_multipart(self, message):
            raise NotImplementedError("Client does not support multipart message")

        def close(self):
            self.that.disconnect(self.identity)

        def __del__(self):
            self.close()


class PipeProto(ProtoBase):
    def __init__(self, mp_context):
        self.server_get, self.server_put = mp_context.Pipe()
        self.client_get, self.client_put = mp_context.Pipe()
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
            return message

        async def recv_multipart(self):
            message = await self.recv()
            return None, message

        async def send(self, message):
            self.in_pipe.send_bytes(message)

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
        logger.info(f"Server started [{os.getpid()}]")
        while True:
            logger.debug("Waiting...")
            try:
                identity, message = await self.proto.recv_multipart()
                result = await self.handle_request(identity, message)
                logger.debug(f"  Function result {result}")
                await self.proto.send_multipart((identity, result))
            except Exception as e:
                logger.error(f"  Catch exception {e}")
                await self.proto.send_multipart((identity, e))

    async def handle_request(self, identity, message):
        method_name, args, kwargs = message
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
            logger.critical("Server task was cancelled.")
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


def RPCClient(cls: Type[T], proto: ProtoBase = None) -> T:
    class RPCClientProxy:
        def __init__(self, target_cls: Type[T], proto: ProtoBase = None):
            self.target_cls = target_cls
            self.proto = proto
            self._init_func_dct()

        def connect(self, proto):
            self.proto = proto

        def _init_func_dct(self):
            for name, value in self.target_cls.__dict__.items():
                if callable(value) and not name.startswith("_"):
                    proxy_method = self._make_rpc_wrapper(name, value)
                    proxy_method.__name__ = name
                    proxy_method.__signature__ = inspect.signature(value)
                    setattr(self.__class__, name, proxy_method)

                    proxy_method = self._make_rpc_sync_wrapper(name, value)
                    proxy_method.__name__ = f"{name}_sync"
                    proxy_method.__signature__ = inspect.signature(value)
                    setattr(self.__class__, f"{name}_sync", proxy_method)

        async def call_rpc(self, name, *args, **kwargs):
            await self.proto.send((name, args, kwargs))
            result = await self.proto.recv()
            if isinstance(result, Exception):
                raise result
            return result

        def call_rpc_sync(self, name, *args, **kwargs):
            asyncio.run(self.proto.send((name, args, kwargs)))
            result = asyncio.run(self.proto.recv())
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

        def _make_rpc_sync_wrapper(self, name, method):
            @wraps(method)
            def rpc_method_sync(self, *args, **kwargs):
                return self.call_rpc_sync(name, *args, **kwargs)

            rpc_method_sync.__signature__ = inspect.signature(method)
            rpc_method_sync.__name__ = f"{name}_sync"
            return rpc_method_sync

    return RPCClientProxy(cls, proto)
