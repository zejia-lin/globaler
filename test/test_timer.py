import time
import torch
import pandas as pd
from globaler import Timer
from globaler.timer import TimeRecord
import torch
import torch.nn.functional as F
import os



csv = Timer.json_to_csv(open("/home/lzj/work/llm-infer/AMotivation/results/timer/2024-08-11_21:29:46.json").read())
with open("/home/lzj/work/llm-infer/AMotivation/results/timer/2024-08-11_21:29:46.csv", "w+") as f:
    f.write(pd.DataFrame(csv).to_csv())

exit(1)


X = torch.randn((4096, 5120), device='cuda')
W = torch.randn((16384, 5120), device='cuda')

stream = torch.cuda.Stream()
timer = Timer()
timer.enabled = False

Y = F.linear(X, W)

with torch.cuda.stream(stream):
    timer.start(name="without sync")
    Y = F.linear(X, W)
    timer.stop()

    timer.start("with sync")
    Y = F.linear(X, W)
    timer.stop(torch.cuda)

timer.start("with sync")
Y = F.linear(X, W)
timer.stop(torch.cuda)

timer.start("Outer", metadata={"key": "value"})
time.sleep(0.1)
timer.start("Inner")
time.sleep(0.2)
timer.stop()
timer.stop()
timer.start("Another")
time.sleep(0.5)
timer.stop()
print(timer.to_json())
print(timer.to_list())
print(timer.to_csv())
print(pd.DataFrame(timer.to_csv()))
timer.save_json("result.json")
timer.save_csv("result.csv")