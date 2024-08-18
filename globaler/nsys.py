import torch

def mark():
  inputs = torch.randn(64, 1, 300)
  module = torch.nn.Conv1d(
      in_channels=1, out_channels=1, kernel_size=5, padding=2, bias=False
  )
  module.weight.data = torch.full_like(module.weight.data, 0.2)
  inputs = inputs.cuda()
  module = module.cuda()
  module(inputs)