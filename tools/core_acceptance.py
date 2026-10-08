"""Source-reference and failure-boundary E2E. Simulation is labeled explicitly."""
import ast
import contextlib
import json
import os
import sys
import threading
import time
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
import tqdm
from PIL import Image
from spandrel import ModelLoader

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project))
from upscale_toolkit.engine import Engine, Cancelled
from upscale_toolkit.image_io import read_image
from upscale_toolkit.jobs import scan_inputs, run_jobs
from upscale_toolkit.options import Options
from e2e import fixture

folder = project / 'artifacts' / 'core'
folder.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=folder / 'failures.log', level=logging.INFO, encoding='utf-8')
source_root = Path(sys.argv[1])
evidence = []


def record(name, **details):
    evidence.append({'scenario': name, **details})
    print(name, 'OK', flush=True)


def extract(relative, names, namespace):
    source = (source_root / relative).read_text(encoding='utf-8-sig')
    parsed = ast.parse(source)
    selected = [n for n in parsed.body if getattr(n, 'name', None) in names]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_root / relative), 'exec'), namespace)


torch.set_num_threads(8)
namespace = {'np': np, 'torch': torch, 'tqdm': tqdm, 'Image': Image, 'Callable': __import__('typing').Callable,
             'math': __import__('math'), 'namedtuple': __import__('collections').namedtuple,
             'logger': __import__('logging').getLogger('forge-reference'),
             'devices': SimpleNamespace(without_autocast=contextlib.nullcontext),
             'torch_utils': SimpleNamespace(get_param=lambda model: next(model.model.parameters())),
             'shared': SimpleNamespace(state=SimpleNamespace(interrupted=False), opts=SimpleNamespace(enable_upscale_progressbar=False))}
extract('modules/images.py', {'Grid', 'split_grid', 'combine_grid'}, namespace)
namespace['images'] = SimpleNamespace(**{name: namespace[name] for name in ('Grid', 'split_grid', 'combine_grid')})
extract('modules/upscaler_utils.py', {'_model', 'pil_image_to_torch_bgr', 'torch_bgr_to_pil_image',
                                     'upscale_pil_patch', 'upscale_with_model_cpu'}, namespace)
original = fixture(folder / 'reference.png', size=(64, 48))
engine = Engine()
opts = Options(device='cuda', scale=2, tile=32, overlap=8, mode='blend')
references = {}
for name, filename in [('ultrasharp', '4x-UltraSharpV2.pth'), ('scunet', 'ScuNET.pth')]:
    descriptor = ModelLoader().load_from_file(str(project / 'model' / filename)).eval().float().cuda()
    ref = namespace['upscale_with_model_cpu'](descriptor, original, tile_size=32, tile_overlap=8)
    references[name] = ref.resize((128, 96), Image.Resampling.LANCZOS)
    del descriptor
    torch.cuda.empty_cache()
reference = Image.blend(references['ultrasharp'], references['scunet'], .25)
actual = engine.process(original, opts)
assert actual.tobytes() == reference.tobytes(), 'Forge reference mismatch'
record('forge-original-functions-reference', exact_pixels=True, size=list(actual.size),
       boundary='Original functions executed in isolated namespace; not live Forge UI')

start = time.perf_counter()
torch.cuda.reset_peak_memory_stats()
large = fixture(folder / 'representative.png', size=(513, 385))
result = engine.process(large, Options(device='cuda', scale=2, tile=128, overlap=16))
record('representative-multi-tile', input=list(large.size), output=list(result.size),
       seconds=round(time.perf_counter() - start, 3), peak_allocated_mib=round(torch.cuda.max_memory_allocated() / 2**20, 1))

source = folder / 'inputs'
fixture(source / 'a.png', parameters='parameter A')
fixture(source / 'b.png', parameters='parameter B')
root, files = scan_inputs(source, folder / 'outputs')
cancel = threading.Event()
cancel.set()
pre = run_jobs(engine, root, files, folder / 'pre-cancel', Options(device='cuda'), cancel=cancel)
assert pre['success'] == 0 and pre['pending'] == 2
record('cancel-before-first-file', summary=pre)
cancel.clear()


def between(kind, data):
    if kind == 'result' and data['status'] == 'success':
        cancel.set()


between_summary = run_jobs(engine, root, files, folder / 'between', Options(mode='denoise', device='cuda'), between, cancel)
assert between_summary['success'] == 1 and between_summary['pending'] == 1
record('cancel-between-files', summary=between_summary)

empty = folder / 'empty-models'
empty.mkdir(exist_ok=True)
missing = run_jobs(Engine(empty), root, files[:1], folder / 'missing-output', Options(device='cpu'))
assert missing['failed'] == 1 and missing['success'] == 0
record('missing-model-real', summary=missing)
(empty / '4x-UltraSharpV2.pth').write_bytes(b'corrupt model')
corrupt = run_jobs(Engine(empty), root, files[:1], folder / 'corrupt-output', Options(device='cpu'))
assert corrupt['failed'] == 1 and corrupt['success'] == 0
record('corrupt-model-real', summary=corrupt)
blocked = folder / 'not-a-directory'
blocked.write_text('file in place of output directory', encoding='utf-8')
bad_output = run_jobs(engine, root, files[:1], blocked, Options(mode='denoise', device='cuda'))
assert bad_output['failed'] == 1
record('unwritable-output-path-real', summary=bad_output)

old_patch = engine.patch


def oom(*args):
    raise torch.cuda.OutOfMemoryError('simulated E2E boundary')


engine.patch = oom
simulated = run_jobs(engine, root, files[:1], folder / 'oom', Options(device='cuda'))
engine.patch = old_patch
assert simulated['failed'] == 1 and simulated['success'] == 0
record('oom-simulated', summary=simulated, boundary='Exception injection; not real GPU exhaustion')
original_available = torch.cuda.is_available
torch.cuda.is_available = lambda: False
try:
    unavailable = run_jobs(engine, root, files[:1], folder / 'cuda-unavailable', Options(device='cuda'))
    assert unavailable['failed'] == 1
finally:
    torch.cuda.is_available = original_available
record('cuda-unavailable-simulated', summary=unavailable, boundary='Availability injection; hardware has CUDA')

for fmt in ('png', 'jpg', 'webp'):
    summary = run_jobs(engine, root, files, folder / ('metadata-' + fmt), Options(mode='denoise', device='cuda', format=fmt))
    assert summary['success'] == 2
    for index, item in enumerate(summary['records']):
        _, _, parameters, _ = read_image(item['output'])
        assert ('parameter A' if index == 0 else 'parameter B') in parameters
        assert ('parameter B' if index == 0 else 'parameter A') not in parameters
    record('metadata-batch-' + fmt, summary=summary)
engine.release()
(folder / 'report.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
