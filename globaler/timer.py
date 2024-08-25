import asyncio
import threading
import time
import json
from typing import Any, Dict, List
import pandas as pd
import uuid
import torch

from .enabler import DebugOnly


class TimeRecord:
    
    CUDA_STREAM_KEY = "_cuda_stream"
    
    def __init__(self, *, start: float, name=None, metadata: dict = None, index: int = None, uid: str = None):
        self.name = name or "unamed"
        self.start = start
        self.metadata = metadata
        self.index = index
        self.uid = uid or str(uuid.uuid4())
        self.end: float = 0
        self.cuda_duration = None
        self.childs = []
        self.parent = None
        if metadata and self.CUDA_STREAM_KEY in metadata:
            self.stream = metadata[self.CUDA_STREAM_KEY]
            self.start_event = torch.cuda.Event(enable_timing=True)
            self.end_event = torch.cuda.Event(enable_timing=True)
            self.start_event.record(self.stream)

    @classmethod
    def from_args(cls, name, start, metadata, index, end, childs, duration):
        record = cls(start=start, name=name, metadata=metadata, index=index)
        record.end = end
        for child_dict in childs:
            kid = cls.from_args(**child_dict)
            kid.parent = record
            record.childs.append(kid)
        return record

    def stop(self, end: float):
        self.end = end
        if (
            self.metadata
            and self.CUDA_STREAM_KEY in self.metadata
        ):
            self.end_event.record(self.stream)
            self.end_event.synchronize()
            self.cuda_duration = self.start_event.elapsed_time(self.end_event)
            self.metadata.pop(self.CUDA_STREAM_KEY)
            self.metadata["cuda"] = self.cuda_duration

    def add(self, record):
        record.parent = self
        self.childs.append(record)

    def __str__(self) -> str:
        if len(self.childs) > 0:
            childs = f", {str(self.childs)}"
        else:
            childs = ""
        return f"('{self.name}'={self.duration:.3f}s{childs})"

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def duration(self):
        return self.end - self.start

    def to_dict(self):
        return {
            "index": self.index,
            "uid": self.uid,
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "metadata": self.metadata,
            "childs": [child.to_dict() for child in self.childs],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=4)

    def to_list(self):
        def flatten_obj(self):
            flat_list = [self]
            for child in self.childs:
                flat_list.extend(flatten_obj(child))
            return flat_list

        flat = flatten_obj(self)
        ret = []
        for obj in flat:
            ret.append(
                {
                    "index": obj.index,
                    "uid": obj.uid,
                    "name": obj.name,
                    "start": obj.start,
                    "end": obj.end,
                    "duration": obj.duration,
                    "metadata": obj.metadata,
                }
            )
            if obj.metadata is not None:
                ret[-1].update(obj.metadata)
        return ret


class Timer(DebugOnly):
    def __init__(self):
        self.records: List[TimeRecord] = []
        self.runnings: Dict[str, TimeRecord] = {}
        self.counter = 0
        self.stash_dict: Dict[str, TimeRecord] = {}

    def _last_n_record(self, n):
        rev = reversed(self.runnings.values())
        for i in range(n):
            ret = next(rev)
        return ret

    def stash(self, key: str, record: TimeRecord):
        self.stash_dict[key] = record

    def unstash(self, key: str):
        return self.stash_dict.pop(key)

    def start(self, name: str = None, metadata: Dict[str, Any] = None, parent=None, cuda=False, stream=None):
        self.counter += 1
        uid = str(uuid.uuid4())
        if name is None:
            name = f"#{self.counter}"
        if cuda:
            if metadata is None:
                metadata = {}
            metadata[TimeRecord.CUDA_STREAM_KEY] = stream
        cur = TimeRecord(start=time.time(), name=name, metadata=metadata, index=self.counter, uid=uid)
        self.runnings[uid] = cur
        if parent is not None:
            parent.add(cur)
        elif len(self.runnings) == 1:
            self.records.append(cur)
        else:
            self._last_n_record(2).add(cur)
        return cur

    def stop(self, synchronizable=None, record: TimeRecord = None):
        if len(self.runnings) == 0:
            raise RuntimeError("No timer is running.")
        if synchronizable is not None:
            synchronizable.synchronize()
        if record is None:
            record = self._last_n_record(1)
        record.stop(time.time())
        self.runnings.pop(record.uid)

    def to_json(self):
        return json.dumps([record.to_dict() for record in self.records], indent=4)

    def save_json(self, filename):
        with open(filename, "w+") as f:
            f.write(self.to_json())

    @classmethod
    def _init_from_json(cls, loader, path_or_json):
        items = loader(path_or_json)
        timer = cls()
        for item in items:
            record = TimeRecord.from_args(**item)
            timer.records.append(record)
        return timer

    @classmethod
    def from_json(cls, json_str):
        return cls._init_from_json(json.loads, json_str)

    @classmethod
    def read_json(cls, path):
        with open(path, "r") as fin:
            return cls._init_from_json(json.load, fin)

    def to_list(self):
        ret = []
        for record in self.records:
            ret.extend(record.to_list())
        return ret

    def save_list(self, filename):
        with open(filename, "w+") as f:
            f.write(json.dumps(self.to_list(), indent=2))

    def to_csv(self):
        ret = {
            "index": [],
            "uid": [],
            "name": [],
            "start": [],
            "end": [],
            "duration": [],
            "metadata": [],
        }
        for record in self.records:
            flat = record.to_list()
            for item in flat:
                ret["index"].append(item["index"])
                ret["uid"].append(item["uid"])
                ret["name"].append(item["name"])
                ret["start"].append(item["start"])
                ret["end"].append(item["end"])
                ret["duration"].append(item["duration"])
                ret["metadata"].append(str(item["metadata"]))
        return ret

    def to_dataframe(self):
        return pd.DataFrame(self.to_csv())

    def save_csv(self, filename):
        df = pd.DataFrame(self.to_csv())
        df.to_csv(filename, index=False)

    def __str__(self) -> str:
        ret = f"Timer<{hex(id(self))}> [\n"
        tab = "  "
        for node in self.records:
            ret += tab + str(node) + "\n"
        ret += "]"
        return ret

    def __repr__(self) -> str:
        return self.__str__()


class AsyncTimer(Timer):
    def __init__(self):
        super().__init__()
