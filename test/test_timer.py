import time
import torch
from globaler import Timer


stream = torch.cuda.Stream()
timer = Timer()

with torch.cuda.stream(stream):
    torch.linalg.eig(torch.randn(1000, 1000).cuda())
    timer.start("sync")
    torch.linalg.eig(torch.randn(1000, 1000).cuda())
    timer.stop(stream)
    timer.start("nosync")
    torch.linalg.eig(torch.randn(1000, 1000).cuda())
    timer.stop()
    

timer.start("Outer", metadata={"key": "value"})
time.sleep(0.1)
timer.start("Inner")
time.sleep(0.2)
timer.stop()
timer.stop()
timer.start("Another")
time.sleep(0.5)
timer.stop()
print(timer.as_json())
print(timer.flatten())
timer.to_json("result.json")