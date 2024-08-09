# Nested Timer

## Install

```python
git clone https://github.com/zejia-lin/globaler
pip install .
```

## Quick Start

The timer can be nested, and contains metadata

```python
from globaler import Timer

timer = Timer()
timer.start("End to end")
timer.start("work_1")
work_1()
timer.stop()
timer.start("work_2")
work_2()
timer.stop()
timer.stop()
print(timer.as_json())
timer.save_json("result.json")
```
