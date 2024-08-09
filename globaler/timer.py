import time
import json
import pandas as pd


class TimeRecord:
    def __init__(self, start: float, name=None, metadata: dict = None, id: int = None):
        self.name = name or "unamed"
        self.start = start
        self.metadata = metadata
        self.id = id
        self.end: float = 0
        self.childs = []
        self.parent = None

    def stop(self, end: float):
        self.end = end

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
            "id": self.id,
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
            "metadata": self.metadata,
            "childs": [child.to_dict() for child in self.childs],
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_list(self):
        def flatten_obj(self):
            flat_list = [self]
            for child in self.childs:
                flat_list.extend(flatten_obj(child))
            return flat_list
        
        flat = flatten_obj(self)
        ret = []
        for obj in flat:
            ret.append({
                "id": obj.id,
                "name": obj.name,
                "start": obj.start,
                "end": obj.end,
                "duration": obj.duration,
                "metadata": obj.metadata,
            })
            if obj.metadata is not None:
                ret[-1].update(obj.metadata)
        return ret


class Timer:
    def __init__(self):
        self.records: list[TimeRecord] = []
        self.runnings = []
        self.counter = 0

    def start(self, name: str = None, metadata = None):
        self.counter += 1
        if name is None:
            name = f"#{self.counter}"
        cur = TimeRecord(start=time.time(), name=name, metadata=metadata, id=self.counter)
        self.runnings.append(cur)
        if len(self.runnings) == 1:
            self.records.append(cur)
        else:
            self.runnings[0].add(cur)

    def stop(self, synchronizable=None):
        if len(self.runnings) == 0:
            raise RuntimeError("No timer is running.")
        if synchronizable is not None:
            synchronizable.synchronize()
        self.runnings[-1].stop(time.time())
        self.runnings.pop()

    def to_json(self):
        return json.dumps([record.to_dict() for record in self.records], indent=2)

    def save_json(self, filename):
        with open(filename, "w+") as f:
            f.write(self.to_json())
            
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
            "id": [],
            "name": [],
            "start": [],
            "end": [],
            "duration": [],
            "metadata": [],
        }
        for record in self.records:
            flat = record.to_list()
            for item in flat:
                ret["id"].append(item["id"])
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

