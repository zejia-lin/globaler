# Nested Timer

The timer can be nested and includes metadata.

# Install

```python
git clone https://github.com/zejia-lin/globaler
pip install .
```

# Quick Start

## Simple Usage


```python
from globaler import Timer

timer = Timer()

timer.start("End to end")
timer.start("work_1", metadata={"m": 1024, "n": 512, "k": 2048})
work_1()
timer.stop()

timer.start("work_2")
work_2()
timer.stop()
timer.stop() # stops the end to end timer
```

## Global Timer

There is a global timer to facilitate timing in many files.

```python
from globaler import getTimer()
timer = getTimer()
```

## Getting Results

The `Timer` class includes several ways to convert the results.

- `to_json`/`save_json`: returns a nested json.
- `to_csv`/`save_csv`: returns a `dict` that can be passed to `pd.Dataframe(timer.to_csv())`
- `to_dataframe`: returns a pandas dataframe.
- `to_list`/`save_list`: returns a plain list.

Examples:

```python
# Json
print(timer.to_json())
timer.save_json("result.json")

# CSV
print(timer.to_csv())
print(timer.to_dataframe())
timer.save_csv("results.csv")
```

## Synchronize

GPU tasks like `torch` may have to call `torch.cuda.synchronize()` before stopping the timer.

```python
import torch
import torch.nn.functional as F

X = torch.randn((2048, 4096), device='cuda')
W = torch.randn((5120, 4096), device='cuda')
Y = F.linear(X, W) # warmup

timer = Timer()
timer.start("without sync")
Y = F.linear(X, W)
timer.stop()

timer.start("with sync")
Y = F.linear(X, W)
timer.stop(torch.cuda)
```

Synchronizing CUDA stream.

```python
stream = torch.cuda.Stream()
with torch.cuda.stream(stream):
    timer.start("stream")
    Y = F.linear(X, W)
    timer.stop(stream)
```

Possible output.
```csv
   id          name         start           end  duration          metadata
0   1  without sync  1.723192e+09  1.723192e+09  0.000340              None
1   2     with sync  1.723192e+09  1.723192e+09  0.110201              None
2   3        stream  1.723192e+09  1.723192e+09  0.110122              None
```
